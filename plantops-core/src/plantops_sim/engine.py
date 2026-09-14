from __future__ import annotations

import hashlib
import heapq
import random
from collections import Counter
from dataclasses import asdict
from typing import Any

from .model import (
    Buffer,
    EventRecord,
    Machine,
    MachineState,
    OrderConfig,
    OrderState,
    OrderStatus,
    Scenario,
)


class SimulationDomainError(Exception):
    """Base class for invalid simulation-domain operations."""


class UnknownMachineError(SimulationDomainError):
    def __init__(self, machine_id: str) -> None:
        super().__init__(f"Machine '{machine_id}' was not found")


class MachineNotDownError(SimulationDomainError):
    def __init__(self, machine_id: str, state: MachineState) -> None:
        super().__init__(f"Machine '{machine_id}' is {state.value}, not DOWN")


class PendingRepairEventError(SimulationDomainError):
    def __init__(self, machine_id: str) -> None:
        super().__init__(f"Machine '{machine_id}' has no pending repair event")


class RandomStreams:
    """Stable named PRNG streams; Python's randomized hash is never used."""

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._streams: dict[str, random.Random] = {}

    def get(self, name: str) -> random.Random:
        if name not in self._streams:
            digest = hashlib.sha256(f"{self.seed}:{name}".encode()).digest()
            self._streams[name] = random.Random(int.from_bytes(digest[:8], "big"))
        return self._streams[name]


class ProductionLineSimulation:
    """Authoritative discrete-event model for a sequential production line."""

    def __init__(self, scenario: Scenario, *, seed: int) -> None:
        self.scenario = scenario
        self.seed = seed
        self.clock = 0.0
        self._sequence = 0
        self._events: list[
            tuple[float, int, int, str, str | None, int | None]
        ] = []
        self._cancelled_event_ids: set[int] = set()
        self._pending_repair_event_ids: dict[str, int] = {}
        self.rng = RandomStreams(seed)
        self.event_log: list[EventRecord] = []
        self._completion_recorded = False
        self.buffers = {
            buffer_id: Buffer(buffer_id, capacity)
            for buffer_id, capacity in scenario.buffer_capacities.items()
        }
        for unit_id in range(1, scenario.raw_material_units + 1):
            self.buffers["raw"].put(unit_id)
        self.machines: dict[str, Machine] = {}
        previous_buffer = "raw"
        for index, stage in enumerate(scenario.stages):
            output = "finished" if index == len(scenario.stages) - 1 else f"after_{stage.id}"
            self.machines[stage.id] = Machine(stage, previous_buffer, output)
            previous_buffer = output
        self.orders: dict[str, OrderState] = {}
        self._urgent_order_id: str | None = None
        self._allocated_order_units: set[int] = set()
        self._record("SIMULATION_STARTED", detail=f"seed={seed}")
        self._initialize_orders()

    def _record(self, kind: str, machine_id: str | None = None, unit_id: int | None = None, detail: str = "") -> None:
        self.event_log.append(EventRecord(round(self.clock, 6), kind, machine_id, unit_id, detail))

    def _schedule(
        self,
        time: float,
        kind: str,
        target_id: str | None = None,
        unit_id: int | None = None,
        *,
        event_phase: int = 0,
    ) -> int:
        self._sequence += 1
        heapq.heappush(
            self._events,
            (time, event_phase, self._sequence, kind, target_id, unit_id),
        )
        return self._sequence

    def _cancel_scheduled_event(self, event_id: int) -> None:
        self._cancelled_event_ids.add(event_id)

    def _initialize_orders(self) -> None:
        order_configs = list(self.scenario.orders)
        if self.scenario.urgent_order_rule is not None:
            rule = self.scenario.urgent_order_rule
            urgent_rng = self.rng.get("orders:urgent")
            arrival = float(
                urgent_rng.randint(
                    rule.min_arrival_minute,
                    rule.max_arrival_minute,
                )
            )
            urgent_order = OrderConfig(
                id=rule.id,
                quantity=urgent_rng.randint(rule.min_quantity, rule.max_quantity),
                release_minute=arrival,
                due_minute=arrival + rule.lead_time_minutes,
                priority=rule.priority,
            )
            order_configs.append(urgent_order)
            self._urgent_order_id = urgent_order.id

        for config in order_configs:
            if config.id in self.orders:
                raise ValueError(f"Duplicate order ID: {config.id}")
            order = OrderState.from_config(config)
            self.orders[order.id] = order
            self._schedule(
                order.due_minute,
                "ORDER_DUE",
                order.id,
                event_phase=1,
            )
            if order.release_minute <= self.clock:
                self._release_order(order)
            else:
                self._schedule(order.release_minute, "ORDER_RELEASED", order.id)

    def _release_order(self, order: OrderState) -> None:
        if order.status != OrderStatus.PENDING:
            return
        order.status = OrderStatus.ACTIVE
        detail = self._order_event_detail(order)
        if order.id == self._urgent_order_id:
            self._record("URGENT_ORDER_RECEIVED", detail=detail)
        self._record("ORDER_RELEASED", detail=detail)

    def _mark_order_due(self, order: OrderState) -> None:
        if order.due_reached:
            return
        order.due_reached = True
        self._record("ORDER_DUE", detail=f"order_id={order.id}")
        if order.remaining_quantity > 0:
            order.was_late = True
            order.status = OrderStatus.LATE
            self._record(
                "ORDER_LATE",
                detail=f"order_id={order.id};remaining={order.remaining_quantity}",
            )

    @staticmethod
    def _order_event_detail(order: OrderState) -> str:
        return (
            f"order_id={order.id};quantity={order.requested_quantity};"
            f"release_minute={order.release_minute:g};"
            f"due_minute={order.due_minute:g};priority={order.priority}"
        )

    def _allocate_good_unit(self, unit_id: int) -> None:
        if unit_id in self._allocated_order_units:
            raise RuntimeError(f"Unit {unit_id} was already allocated to an order")
        candidates = [
            order
            for order in self.orders.values()
            if order.status != OrderStatus.PENDING and order.remaining_quantity > 0
        ]
        if not candidates:
            return

        order = min(
            candidates,
            key=lambda candidate: (
                candidate.due_minute,
                -candidate.priority,
                candidate.id,
            ),
        )
        order.fulfilled_quantity += 1
        if self.clock <= order.due_minute:
            order.on_time_fulfilled_quantity += 1
        else:
            order.late_fulfilled_quantity += 1
        self._allocated_order_units.add(unit_id)

        if order.remaining_quantity == 0:
            if order.was_late or order.late_fulfilled_quantity:
                order.status = OrderStatus.COMPLETED_LATE
            else:
                order.status = OrderStatus.COMPLETED_ON_TIME

    def _try_start(self, machine: Machine) -> bool:
        if machine.state in {MachineState.RUNNING, MachineState.DOWN}:
            return False
        input_buffer = self.buffers[machine.input_buffer]
        output_buffer = self.buffers[machine.output_buffer]
        if not input_buffer.units:
            if machine.state != MachineState.STARVED:
                machine.state = MachineState.STARVED
                self._record("MACHINE_STARVED", machine.config.id)
            return False
        if not output_buffer.can_take():
            if machine.state != MachineState.BLOCKED:
                machine.state = MachineState.BLOCKED
                self._record("MACHINE_BLOCKED", machine.config.id)
            return False
        unit_id = input_buffer.get()
        cycle_rng = self.rng.get(f"cycle:{machine.config.id}")
        cycle = max(0.05, cycle_rng.uniform(
            machine.config.ideal_cycle_minutes - machine.config.cycle_jitter,
            machine.config.ideal_cycle_minutes + machine.config.cycle_jitter,
        ))
        machine.state = MachineState.RUNNING
        machine.busy_unit = unit_id
        self._record("PROCESS_STARTED", machine.config.id, unit_id)
        self._schedule(self.clock + cycle, "PROCESS_COMPLETED", machine.config.id, unit_id)
        return True

    def _attempt_all_starts(self) -> None:
        made_progress = True
        while made_progress:
            made_progress = any(self._try_start(machine) for machine in self.machines.values())

    def _complete_process(self, machine: Machine, unit_id: int) -> None:
        if machine.state != MachineState.RUNNING or machine.busy_unit != unit_id:
            raise RuntimeError("Invalid completion event")
        elapsed = self.clock - next(
            event.time for event in reversed(self.event_log)
            if event.kind == "PROCESS_STARTED" and event.machine_id == machine.config.id and event.unit_id == unit_id
        )
        machine.run_minutes += elapsed
        machine.processed_units += 1
        machine.busy_unit = None
        machine.state = MachineState.IDLE
        if machine.config.scrap_probability and self.rng.get(f"scrap:{machine.config.id}").random() < machine.config.scrap_probability:
            machine.scrap_units += 1
            self._record("UNIT_SCRAPPED", machine.config.id, unit_id)
        else:
            self.buffers[machine.output_buffer].put(unit_id)
            self._record("PROCESS_COMPLETED", machine.config.id, unit_id)
            if machine.output_buffer == "finished":
                self._allocate_good_unit(unit_id)
        if machine.config.failure_probability and self.rng.get(f"failure:{machine.config.id}").random() < machine.config.failure_probability:
            machine.state = MachineState.DOWN
            machine.failures += 1
            repair = self.rng.get(f"repair:{machine.config.id}").uniform(
                machine.config.repair_min_minutes, machine.config.repair_max_minutes
            )
            self._record("MACHINE_FAILED", machine.config.id, detail=f"repair_eta={repair:.2f}")
            repair_event_id = self._schedule(
                self.clock + repair,
                "REPAIR_COMPLETED",
                machine.config.id,
            )
            self._pending_repair_event_ids[machine.config.id] = repair_event_id

    def _repair_machine(self, machine: Machine) -> None:
        if machine.state != MachineState.DOWN:
            return
        failure = next(event for event in reversed(self.event_log) if event.kind == "MACHINE_FAILED" and event.machine_id == machine.config.id)
        machine.down_minutes += self.clock - failure.time
        machine.state = MachineState.IDLE
        self._record("REPAIR_COMPLETED", machine.config.id)

    def expedite_repair(self, machine_id: str) -> None:
        """Immediately repair a failed machine and invalidate its scheduled repair."""
        machine = self._resolve_machine(machine_id)
        if machine.state != MachineState.DOWN:
            raise MachineNotDownError(machine.config.name, machine.state)

        repair_event_id = self._pending_repair_event_ids.get(machine.config.id)
        if repair_event_id is None:
            raise PendingRepairEventError(machine.config.name)

        self._cancel_scheduled_event(repair_event_id)
        del self._pending_repair_event_ids[machine.config.id]
        self._record("REPAIR_EXPEDITED", machine.config.id)
        self._repair_machine(machine)

    def _resolve_machine(self, machine_id: str) -> Machine:
        normalized_id = machine_id.strip().casefold().replace("-", "_")
        machine = self.machines.get(normalized_id)
        if machine is None:
            normalized_name = machine_id.strip().casefold()
            machine = next(
                (
                    candidate
                    for candidate in self.machines.values()
                    if candidate.config.name.casefold() == normalized_name
                ),
                None,
            )
        if machine is None:
            raise UnknownMachineError(machine_id)
        return machine

    def _effective_down_minutes(self, machine: Machine) -> float:
        """Include an unfinished repair when the simulation stops mid-downtime."""
        effective_down = machine.down_minutes
        if machine.state == MachineState.DOWN:
            failure = next(
                event
                for event in reversed(self.event_log)
                if event.kind == "MACHINE_FAILED" and event.machine_id == machine.config.id
            )
            effective_down += self.clock - failure.time
        return effective_down

    def advance_to(self, until_minutes: float) -> dict[str, Any]:
        """Advance to an absolute simulation time while preserving all state."""
        if until_minutes < self.clock:
            raise ValueError(
                f"Cannot move simulation time backwards from {self.clock} to {until_minutes}"
            )

        self._attempt_all_starts()
        while self._events and self._events[0][0] <= until_minutes:
            time, _, event_id, kind, target_id, unit_id = heapq.heappop(self._events)
            if event_id in self._cancelled_event_ids:
                self._cancelled_event_ids.remove(event_id)
                continue
            self.clock = time
            if kind == "PROCESS_COMPLETED":
                machine = self.machines[target_id] if target_id else None
                assert machine is not None and unit_id is not None
                self._complete_process(machine, unit_id)
            elif kind == "REPAIR_COMPLETED":
                machine = self.machines[target_id] if target_id else None
                assert machine is not None
                if self._pending_repair_event_ids.get(machine.config.id) != event_id:
                    continue
                del self._pending_repair_event_ids[machine.config.id]
                self._repair_machine(machine)
            elif kind == "ORDER_RELEASED":
                assert target_id is not None
                self._release_order(self.orders[target_id])
            elif kind == "ORDER_DUE":
                assert target_id is not None
                self._mark_order_due(self.orders[target_id])
            else:
                raise RuntimeError(f"Unknown event type: {kind}")
            self._attempt_all_starts()
        self.clock = until_minutes
        return self.summary()

    def advance_by(self, minutes: float) -> dict[str, Any]:
        """Advance by a relative number of simulated minutes."""
        if minutes < 0:
            raise ValueError("Advance duration cannot be negative")
        return self.advance_to(self.clock + minutes)

    def run(self, until_minutes: float | None = None) -> dict[str, Any]:
        """Run to a target time and retain the legacy completion event."""
        until = self.scenario.shift_minutes if until_minutes is None else until_minutes
        self.advance_to(until)
        if not self._completion_recorded:
            self._record("SIMULATION_COMPLETED")
            self._completion_recorded = True
        return self.summary()

    def summary(self) -> dict[str, Any]:
        quality_machine = self.machines[self.scenario.stages[-1].id]
        good = self.buffers["finished"].size
        total_quality = quality_machine.processed_units
        quality = good / total_quality if total_quality else 0.0
        machine_metrics = {}
        for machine_id, machine in self.machines.items():
            down_minutes = self._effective_down_minutes(machine)
            availability = max(0.0, (self.clock - down_minutes) / self.clock) if self.clock else 0.0
            performance = min(1.0, (machine.config.ideal_cycle_minutes * machine.processed_units / machine.run_minutes)) if machine.run_minutes else 0.0
            machine_metrics[machine_id] = {
                "state": machine.state.value,
                "processed": machine.processed_units,
                "scrap": machine.scrap_units,
                "failures": machine.failures,
                "run_minutes": round(machine.run_minutes, 3),
                "down_minutes": round(down_minutes, 3),
                "availability": round(availability, 4),
                "performance": round(performance, 4),
            }
        average_availability = sum(item["availability"] for item in machine_metrics.values()) / len(machine_metrics)
        average_performance = sum(item["performance"] for item in machine_metrics.values()) / len(machine_metrics)
        return {
            "seed": self.seed,
            "simulated_minutes": round(self.clock, 3),
            "good_production": good,
            "scrap": quality_machine.scrap_units,
            "quality": round(quality, 4),
            "oee": round(average_availability * average_performance * quality, 4),
            "wip": sum(buffer.size for buffer_id, buffer in self.buffers.items() if buffer_id not in {"raw", "finished"}),
            "raw_material_remaining": self.buffers["raw"].size,
            "machine_metrics": machine_metrics,
            "event_counts": dict(sorted(Counter(event.kind for event in self.event_log).items())),
            "order_summary": self._order_summary(),
        }

    def _order_summary(self) -> dict[str, Any]:
        orders = sorted(
            self.orders.values(),
            key=lambda order: (
                order.release_minute,
                order.due_minute,
                -order.priority,
                order.id,
            ),
        )
        due_orders = [order for order in orders if order.due_reached]
        on_time_orders = [
            order
            for order in due_orders
            if order.on_time_fulfilled_quantity == order.requested_quantity
        ]
        otif = (
            round(len(on_time_orders) / len(due_orders), 4)
            if due_orders
            else None
        )
        return {
            "orders_total": len(orders),
            "orders_released": sum(
                order.status != OrderStatus.PENDING for order in orders
            ),
            "orders_due": len(due_orders),
            "orders_completed": sum(
                order.remaining_quantity == 0 for order in orders
            ),
            "orders_late": sum(order.was_late for order in orders),
            "units_ordered": sum(order.requested_quantity for order in orders),
            "units_delivered": sum(order.fulfilled_quantity for order in orders),
            "units_on_time": sum(
                order.on_time_fulfilled_quantity for order in orders
            ),
            "units_late": sum(order.late_fulfilled_quantity for order in orders),
            "otif": otif,
            "orders": [
                {
                    "id": order.id,
                    "quantity": order.requested_quantity,
                    "fulfilled_quantity": order.fulfilled_quantity,
                    "remaining_quantity": order.remaining_quantity,
                    "release_minute": order.release_minute,
                    "due_minute": order.due_minute,
                    "priority": order.priority,
                    "status": order.status.value,
                }
                for order in orders
            ],
        }

    def digest(self) -> str:
        rows = [asdict(event) for event in self.event_log]
        return hashlib.sha256(repr(rows).encode()).hexdigest()
