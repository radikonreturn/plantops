from __future__ import annotations

import hashlib
import heapq
import random
from collections import Counter
from dataclasses import asdict
from typing import Any

from .living import LivingShift
from .model import (
    Buffer,
    EventRecord,
    FinishedGoodsInventory,
    Machine,
    MachineState,
    OrderConfig,
    OrderState,
    OrderStatus,
    PurchaseOrderState,
    PurchaseOrderStatus,
    Scenario,
    SupplierConfig,
)


MAX_PURCHASE_QUANTITY = 1_000


class SimulationDomainError(Exception):
    """Base class for invalid simulation-domain operations."""


class ShiftActionUnavailableError(SimulationDomainError):
    """A bounded shift action is unavailable in the current state."""


class UnknownPurchaseOrderError(SimulationDomainError):
    """The requested purchase order does not exist."""


class UnknownMachineError(SimulationDomainError):
    def __init__(self, machine_id: str) -> None:
        super().__init__(f"Machine '{machine_id}' was not found")


class MachineNotDownError(SimulationDomainError):
    def __init__(self, machine_id: str, state: MachineState) -> None:
        super().__init__(f"Machine '{machine_id}' is {state.value}, not DOWN")


class PendingRepairEventError(SimulationDomainError):
    def __init__(self, machine_id: str) -> None:
        super().__init__(f"Machine '{machine_id}' has no pending repair event")


class UnknownOrderError(SimulationDomainError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"Order '{order_id}' was not found")


class OrderCannotBeReprioritizedError(SimulationDomainError):
    def __init__(self, order_id: str, status: OrderStatus) -> None:
        super().__init__(
            f"Order '{order_id}' cannot be reprioritized while {status.value}"
        )


class InvalidOrderPriorityError(SimulationDomainError):
    def __init__(self, priority: object) -> None:
        super().__init__(
            f"Order priority must be an integer from 0 through 100; got {priority!r}"
        )


class UnknownSupplierError(SimulationDomainError):
    def __init__(self, supplier_id: str) -> None:
        super().__init__(f"Supplier '{supplier_id}' was not found")


class InvalidPurchaseQuantityError(SimulationDomainError):
    def __init__(self, quantity: object) -> None:
        super().__init__(
            "Purchase quantity must be an integer from 1 through "
            f"{MAX_PURCHASE_QUANTITY}; got {quantity!r}"
        )


class MachineCannotStartPreventiveMaintenanceError(SimulationDomainError):
    def __init__(self, machine_id: str, state: MachineState) -> None:
        super().__init__(
            f"Machine '{machine_id}' cannot start preventive maintenance "
            f"while {state.value}"
        )


class PreventiveMaintenanceNotConfiguredError(SimulationDomainError):
    def __init__(self, machine_id: str) -> None:
        super().__init__(
            f"Machine '{machine_id}' has no preventive maintenance configured"
        )


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
        self.living: LivingShift | None = None
        self.scenario = scenario
        self.seed = seed
        self.clock = 0.0
        self._sequence = 0
        self._events: list[
            tuple[float, int, int, str, str | None, int | None]
        ] = []
        self._cancelled_event_ids: set[int] = set()
        self._pending_repair_event_ids: dict[str, int] = {}
        self._pending_maintenance_event_ids: dict[str, int] = {}
        self.rng = RandomStreams(seed)
        self.event_log: list[EventRecord] = []
        self._completion_recorded = False
        self._next_raw_unit_id = scenario.raw_material_units + 1
        self._purchase_order_sequence = 0
        self.purchase_orders: dict[str, PurchaseOrderState] = {}
        self.suppliers: dict[str, SupplierConfig] = {}
        for supplier in scenario.suppliers:
            if supplier.id in self.suppliers:
                raise ValueError(f"Duplicate supplier ID: {supplier.id}")
            self.suppliers[supplier.id] = supplier
        self.buffers: dict[str, Buffer] = {
            buffer_id: (
                FinishedGoodsInventory(buffer_id, capacity)
                if buffer_id == "finished"
                else Buffer(buffer_id, capacity)
            )
            for buffer_id, capacity in scenario.buffer_capacities.items()
        }
        finished_goods = self.buffers["finished"]
        if not isinstance(finished_goods, FinishedGoodsInventory):
            raise ValueError("Scenario must define a finished-goods buffer")
        self.finished_goods = finished_goods
        for unit_id in range(1, scenario.raw_material_units + 1):
            self.buffers["raw"].put(unit_id)
        # Carry-in WIP belongs to the preceding shift, with distinct unit IDs.
        for buffer_id, quantity in scenario.initial_wip:
            for _ in range(quantity):
                self.buffers[buffer_id].put(self._next_raw_unit_id)
                self._next_raw_unit_id += 1
        self.machines: dict[str, Machine] = {}
        previous_buffer = "raw"
        for index, stage in enumerate(scenario.stages):
            output = "finished" if index == len(scenario.stages) - 1 else f"after_{stage.id}"
            self.machines[stage.id] = Machine(
                stage, previous_buffer, output, health=stage.initial_health
            )
            previous_buffer = output
        from .equipment import EquipmentSystems
        self.equipment = EquipmentSystems(self) if "laser_01" in self.machines and "test_01" in self.machines else None
        self.orders: dict[str, OrderState] = {}
        self._urgent_order_id: str | None = None
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
        order.status = OrderStatus.LATE if order.was_late else OrderStatus.ACTIVE
        detail = self._order_event_detail(order)
        if order.id == self._urgent_order_id:
            self._record("URGENT_ORDER_RECEIVED", detail=detail)
        self._record("ORDER_RELEASED", detail=detail)
        self._allocate_finished_goods()

    def _mark_order_due(self, order: OrderState) -> None:
        if order.due_reached:
            return
        order.due_reached = True
        self._record("ORDER_DUE", detail=f"order_id={order.id}")
        if order.remaining_quantity > 0:
            order.was_late = True
            if order.status != OrderStatus.PENDING:
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

    def _allocate_finished_goods(self) -> None:
        """Allocate available warehouse units by order priority and unit FIFO."""
        while self.finished_goods.available_unit_ids:
            candidates = [
                order
                for order in self.orders.values()
                if order.status != OrderStatus.PENDING
                and order.remaining_quantity > 0
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
            unit_id = self.finished_goods.allocate_next(order.id)
            order.fulfilled_quantity += 1
            if self.clock <= order.due_minute:
                order.on_time_fulfilled_quantity += 1
            else:
                order.late_fulfilled_quantity += 1
            self._record(
                "ORDER_UNIT_ALLOCATED",
                unit_id=unit_id,
                detail=f"order_id={order.id}",
            )

            if order.remaining_quantity == 0:
                if order.was_late or order.late_fulfilled_quantity:
                    order.status = OrderStatus.COMPLETED_LATE
                else:
                    order.status = OrderStatus.COMPLETED_ON_TIME

    def _try_start(self, machine: Machine) -> bool:
        if machine.state in {
            MachineState.RUNNING,
            MachineState.DOWN,
            MachineState.PLANNED_MAINTENANCE,
        }:
            return False
        if self.equipment and self.equipment.start(machine.config.id):
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
        if self.equipment:
            cycle *= self.equipment.multiplier(machine.config.id)
        if self.living:
            cycle = self.living.cycle_minutes(machine.config.id, unit_id, cycle)
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
        if self.equipment and self.equipment.retest(machine.config.id, unit_id):
            return
        elapsed = self.clock - next(
            event.time for event in reversed(self.event_log)
            if event.kind == "PROCESS_STARTED" and event.machine_id == machine.config.id and event.unit_id == unit_id
        )
        machine.run_minutes += elapsed
        machine.processed_units += 1
        machine.health = max(
            0.0,
            machine.health - machine.config.health_loss_per_processed_unit,
        )
        machine.busy_unit = None
        machine.state = MachineState.IDLE
        rejected = bool(machine.config.scrap_probability and self.rng.get(f"scrap:{machine.config.id}").random() < machine.config.scrap_probability)
        if self.equipment:
            rejected = self.equipment.process(machine.config.id, unit_id, rejected)
        if self.living and not rejected:
            rejected = self.living.latent_defect(machine.config.id, unit_id)
        if self.living:
            self.living.inspection_units.discard(unit_id)
        if rejected:
            machine.scrap_units += 1
            self._record("UNIT_SCRAPPED", machine.config.id, unit_id)
        else:
            self.buffers[machine.output_buffer].put(unit_id)
            self._record("PROCESS_COMPLETED", machine.config.id, unit_id)
            if machine.output_buffer == "finished":
                self._record("FINISHED_GOODS_RECEIVED", unit_id=unit_id)
                self._allocate_finished_goods()
        failure_probability = self._effective_failure_probability(machine)
        if (
            failure_probability
            and self.rng.get(f"failure:{machine.config.id}").random()
            < failure_probability
        ):
            if self.equipment and machine.config.id != "cnc_01":
                condition = self.equipment.conditions[machine.config.id]
                condition.burden = min(100, condition.burden + 12)
                self._record("EQUIPMENT_CONDITION_WORSENED", machine.config.id,
                             detail=self.equipment.impact(machine.config.id))
                return
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

    def _effective_failure_probability(self, machine: Machine) -> float:
        wear_fraction = (100.0 - machine.health) / 100.0
        multiplier = 1.0 + (
            machine.config.wear_based_failure_multiplier * wear_fraction
        )
        if self.living and self.living.fatigue_active:
            multiplier *= 1.2
        return min(1.0, machine.config.failure_probability * multiplier)

    def effective_failure_probability(self, machine_id: str) -> float:
        """Return the machine's current health-adjusted failure probability."""
        return self._effective_failure_probability(self._resolve_machine(machine_id))

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

    def preventive_maintenance_cost(self, machine_id: str) -> float:
        """Return the configured cost for one preventive-maintenance action."""
        return self._resolve_machine(machine_id).config.preventive_maintenance_cost

    def start_preventive_maintenance(self, machine_id: str) -> None:
        """Stop an eligible machine for its configured preventive maintenance."""
        machine = self._resolve_machine(machine_id)
        if self.equipment and machine.config.id in self.equipment.conditions:
            condition = self.equipment.conditions[machine.config.id]
            if condition.pending or condition.active:
                raise ShiftActionUnavailableError("Equipment service already queued or in progress")
        if machine.config.preventive_maintenance_duration <= 0:
            raise PreventiveMaintenanceNotConfiguredError(machine.config.name)
        if machine.state not in {
            MachineState.IDLE,
            MachineState.STARVED,
            MachineState.BLOCKED,
        }:
            raise MachineCannotStartPreventiveMaintenanceError(
                machine.config.name,
                machine.state,
            )

        duration = machine.config.preventive_maintenance_duration
        machine.state = MachineState.PLANNED_MAINTENANCE
        machine.active_maintenance_start_minute = self.clock
        self._record(
            "PLANNED_MAINTENANCE_STARTED",
            machine.config.id,
            detail=(
                f"duration={duration:g};"
                f"cost={machine.config.preventive_maintenance_cost:.2f};"
                f"health={machine.health:g}"
            ),
        )
        event_id = self._schedule(
            self.clock + duration,
            "PLANNED_MAINTENANCE_COMPLETED",
            machine.config.id,
        )
        self._pending_maintenance_event_ids[machine.config.id] = event_id

    def _complete_preventive_maintenance(self, machine: Machine) -> None:
        if (
            machine.state != MachineState.PLANNED_MAINTENANCE
            or machine.active_maintenance_start_minute is None
        ):
            return

        machine.planned_maintenance_minutes += (
            machine.config.preventive_maintenance_duration
        )
        machine.active_maintenance_start_minute = None
        machine.health = 100.0
        machine.maintenance_count += 1
        machine.state = MachineState.IDLE
        if self.equipment:
            self.equipment.restore(machine.config.id)
        self._record("PLANNED_MAINTENANCE_COMPLETED", machine.config.id)

    def reprioritize_order(self, order_id: str, priority: int) -> None:
        """Change the priority used for an order's future warehouse allocations."""
        if type(priority) is not int or not 0 <= priority <= 100:
            raise InvalidOrderPriorityError(priority)

        order = self.orders.get(order_id)
        if order is None:
            raise UnknownOrderError(order_id)
        if order.status == OrderStatus.PENDING or order.remaining_quantity == 0:
            raise OrderCannotBeReprioritizedError(order.id, order.status)
        if order.priority == priority:
            return

        old_priority = order.priority
        order.priority = priority
        self._record(
            "ORDER_PRIORITY_CHANGED",
            detail=(
                f"order_id={order.id};old_priority={old_priority};"
                f"new_priority={priority}"
            ),
        )

    def place_purchase_order(
        self,
        supplier_id: str,
        quantity: int,
    ) -> PurchaseOrderState:
        """Commit a replenishment order and schedule its deterministic receipt."""
        if type(quantity) is not int or not 1 <= quantity <= MAX_PURCHASE_QUANTITY:
            raise InvalidPurchaseQuantityError(quantity)

        supplier = self.suppliers.get(supplier_id)
        if supplier is None:
            raise UnknownSupplierError(supplier_id)

        self._purchase_order_sequence += 1
        purchase_order_id = f"PO-{self._purchase_order_sequence:06d}"
        stream_prefix = f"supplier:{supplier.id}"
        lead_minutes = self.rng.get(f"{stream_prefix}:lead").uniform(
            supplier.min_lead_minutes,
            supplier.max_lead_minutes,
        )
        promised_receipt_minute = self.clock + lead_minutes
        is_late = (
            self.rng.get(f"{stream_prefix}:late").random()
            < supplier.late_probability
        )
        actual_receipt_minute = promised_receipt_minute
        if is_late:
            delay_minutes = supplier.max_delay_minutes * (
                1.0 - self.rng.get(f"{stream_prefix}:delay").random()
            )
            actual_receipt_minute += delay_minutes

        purchase_order = PurchaseOrderState(
            id=purchase_order_id,
            supplier_id=supplier.id,
            quantity=quantity,
            placed_minute=self.clock,
            promised_receipt_minute=promised_receipt_minute,
            unit_cost=supplier.unit_cost,
            total_committed_cost=round(quantity * supplier.unit_cost, 2),
        )
        self.purchase_orders[purchase_order.id] = purchase_order
        receipt_event_id = self._schedule(
            actual_receipt_minute,
            "MATERIAL_RECEIVED",
            purchase_order.id,
        )
        if self.living:
            self.living.register_receipt(purchase_order.id, actual_receipt_minute, receipt_event_id)
        self._record(
            "PURCHASE_ORDER_PLACED",
            detail=(
                f"purchase_order_id={purchase_order.id};"
                f"supplier_id={purchase_order.supplier_id};"
                f"quantity={purchase_order.quantity};"
                "promised_receipt_minute="
                f"{purchase_order.promised_receipt_minute:g};"
                f"unit_cost={purchase_order.unit_cost:.2f};"
                f"total_committed_cost={purchase_order.total_committed_cost:.2f}"
            ),
        )
        return purchase_order

    def _receive_material(self, purchase_order: PurchaseOrderState) -> None:
        if purchase_order.status != PurchaseOrderStatus.OPEN:
            return

        purchase_order.actual_receipt_minute = self.clock
        is_late = self.clock > purchase_order.promised_receipt_minute
        purchase_order.status = (
            PurchaseOrderStatus.RECEIVED_LATE
            if is_late
            else PurchaseOrderStatus.RECEIVED_ON_TIME
        )
        if is_late:
            self._record(
                "PURCHASE_ORDER_LATE",
                detail=(
                    f"purchase_order_id={purchase_order.id};"
                    f"supplier_id={purchase_order.supplier_id};"
                    "promised_receipt_minute="
                    f"{purchase_order.promised_receipt_minute:g};"
                    f"actual_receipt_minute={self.clock:g}"
                ),
            )

        first_unit_id = self._next_raw_unit_id
        for _ in range(purchase_order.quantity):
            self.buffers["raw"].put(self._next_raw_unit_id)
            self._next_raw_unit_id += 1
        last_unit_id = self._next_raw_unit_id - 1
        self._record(
            "MATERIAL_RECEIVED",
            detail=(
                f"purchase_order_id={purchase_order.id};"
                f"supplier_id={purchase_order.supplier_id};"
                f"quantity={purchase_order.quantity};"
                f"first_unit_id={first_unit_id};last_unit_id={last_unit_id};"
                f"status={purchase_order.status.value}"
            ),
        )

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

    def _effective_planned_maintenance_minutes(self, machine: Machine) -> float:
        effective_planned_maintenance = machine.planned_maintenance_minutes
        if (
            machine.state == MachineState.PLANNED_MAINTENANCE
            and machine.active_maintenance_start_minute is not None
        ):
            effective_planned_maintenance += (
                self.clock - machine.active_maintenance_start_minute
            )
        return effective_planned_maintenance

    def advance_to(self, until_minutes: float) -> dict[str, Any]:
        """Advance to an absolute simulation time while preserving all state."""
        if until_minutes < self.clock:
            raise ValueError(
                f"Cannot move simulation time backwards from {self.clock} to {until_minutes}"
            )

        if self.living:
            until_minutes = min(until_minutes, self.living.end_minute)
            if self.clock >= self.living.end_minute:
                return self.summary()
        self._attempt_all_starts()
        while self._events and self._events[0][0] <= until_minutes:
            time, _, event_id, kind, target_id, unit_id = heapq.heappop(self._events)
            if event_id in self._cancelled_event_ids:
                self._cancelled_event_ids.remove(event_id)
                continue
            self.clock = time
            if kind in {"SHIFT_EVENT_START", "SHIFT_EVENT_END"}:
                assert self.living is not None and target_id is not None
                self.living.handle_event(kind, target_id)
            elif kind == "EQUIPMENT_SERVICE_COMPLETED":
                assert self.equipment is not None and target_id is not None
                self.equipment.complete_service(target_id)
            elif kind == "OVERTIME_STARTED":
                self._record("OVERTIME_STARTED", detail="failure_multiplier=1.2;labor_cost_already_committed=600")
            elif kind == "PROCESS_COMPLETED":
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
            elif kind == "MATERIAL_RECEIVED":
                assert target_id is not None
                self._receive_material(self.purchase_orders[target_id])
            elif kind == "PLANNED_MAINTENANCE_COMPLETED":
                machine = self.machines[target_id] if target_id else None
                assert machine is not None
                if (
                    self._pending_maintenance_event_ids.get(machine.config.id)
                    != event_id
                ):
                    continue
                del self._pending_maintenance_event_ids[machine.config.id]
                self._complete_preventive_maintenance(machine)
            else:
                raise RuntimeError(f"Unknown event type: {kind}")
            if self.equipment:
                self.equipment.reconcile()
            if self.living:
                self.living.reconcile()
            if not self.living or self.clock < self.living.end_minute:
                self._attempt_all_starts()
        self.clock = until_minutes
        if self.living:
            self.living.reconcile()
        return self.summary()

    def advance_by(self, minutes: float) -> dict[str, Any]:
        """Advance by a relative number of simulated minutes."""
        if minutes < 0:
            raise ValueError("Advance duration cannot be negative")
        return self.advance_to(self.clock + minutes)

    def run(self, until_minutes: float | None = None) -> dict[str, Any]:
        """Run to a target time and retain the legacy completion event."""
        until = (self.living.end_minute if self.living else self.scenario.shift_minutes) if until_minutes is None else until_minutes
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
            unplanned_downtime = self._effective_down_minutes(machine)
            planned_maintenance = self._effective_planned_maintenance_minutes(machine)
            planned_production_time = max(0.0, self.clock - planned_maintenance)
            availability = (
                max(
                    0.0,
                    (planned_production_time - unplanned_downtime)
                    / planned_production_time,
                )
                if planned_production_time
                else 0.0
            )
            performance = min(1.0, (machine.config.ideal_cycle_minutes * machine.processed_units / machine.run_minutes)) if machine.run_minutes else 0.0
            machine_metrics[machine_id] = {
                "state": machine.state.value,
                "processed": machine.processed_units,
                "scrap": machine.scrap_units,
                "failures": machine.failures,
                "run_minutes": round(machine.run_minutes, 3),
                "down_minutes": round(unplanned_downtime, 3),
                "unplanned_downtime_minutes": round(unplanned_downtime, 3),
                "planned_maintenance_minutes": round(planned_maintenance, 3),
                "maintenance_count": machine.maintenance_count,
                "health": round(machine.health, 3),
                "availability": round(availability, 4),
                "performance": round(performance, 4),
                **(self.equipment.metric(machine_id) if self.equipment else {}),
            }
        average_availability = sum(item["availability"] for item in machine_metrics.values()) / len(machine_metrics)
        average_performance = sum(item["performance"] for item in machine_metrics.values()) / len(machine_metrics)
        finished_goods_available = self.finished_goods.available_size
        finished_goods_allocated = self.finished_goods.allocated_size
        finished_goods_total = self.finished_goods.size
        order_summary = self._order_summary()
        supply_summary = self._supply_summary()
        if finished_goods_total != finished_goods_available + finished_goods_allocated:
            raise RuntimeError("Finished-goods accounting invariant was violated")
        if finished_goods_allocated != order_summary["units_delivered"]:
            raise RuntimeError("Finished-goods allocation accounting was violated")
        return {
            "seed": self.seed,
            "simulated_minutes": round(self.clock, 3),
            "shift_minutes": self.living.end_minute if self.living else self.scenario.shift_minutes,
            **(self.living.snapshot() if self.living else {}),
            **({"equipment_quality": self.equipment.quality_summary(),
                "total_scrap": sum(m.scrap_units for m in self.machines.values())} if self.equipment else {}),
            "good_production": good,
            "scrap": quality_machine.scrap_units,
            "quality": round(quality, 4),
            "oee": round(average_availability * average_performance * quality, 4),
            "wip": sum(buffer.size for buffer_id, buffer in self.buffers.items() if buffer_id not in {"raw", "finished"}),
            "raw_material_remaining": self.buffers["raw"].size,
            "finished_goods_available": finished_goods_available,
            "finished_goods_allocated": finished_goods_allocated,
            "finished_goods_total": finished_goods_total,
            "buffer_levels": {
                buffer_id: buffer.size
                for buffer_id, buffer in self.buffers.items()
            },
            "machine_metrics": machine_metrics,
            "event_counts": dict(sorted(Counter(event.kind for event in self.event_log).items())),
            "order_summary": order_summary,
            "supply_summary": supply_summary,
        }

    def _supply_summary(self) -> dict[str, Any]:
        purchase_orders = [
            self.purchase_orders[purchase_order_id]
            for purchase_order_id in sorted(self.purchase_orders)
        ]
        open_orders = [
            purchase_order
            for purchase_order in purchase_orders
            if purchase_order.status == PurchaseOrderStatus.OPEN
        ]
        received_orders = [
            purchase_order
            for purchase_order in purchase_orders
            if purchase_order.status != PurchaseOrderStatus.OPEN
        ]
        return {
            "raw_material_on_hand": self.buffers["raw"].size,
            "purchase_orders_total": len(purchase_orders),
            "purchase_orders_open": len(open_orders),
            "purchase_orders_received": len(received_orders),
            "purchase_orders_late": sum(
                purchase_order.status == PurchaseOrderStatus.RECEIVED_LATE
                for purchase_order in purchase_orders
            ),
            "inbound_units": sum(
                purchase_order.quantity for purchase_order in open_orders
            ),
            "received_units": sum(
                purchase_order.quantity for purchase_order in received_orders
            ),
            "procurement_committed_cost": round(
                sum(
                    purchase_order.total_committed_cost
                    for purchase_order in purchase_orders
                ),
                2,
            ),
            "purchase_orders": [
                {
                    **({"expedited": purchase_order.id in self.living.expedited,
                        "expedite_cost": self.living.expedited.get(purchase_order.id, 0),
                        "expected_receipt_minute": self.living.receipt_times[purchase_order.id],
                        "supplier_late": self.living.receipt_times[purchase_order.id] > purchase_order.promised_receipt_minute}
                       if self.living else {}),
                    "id": purchase_order.id,
                    "supplier_id": purchase_order.supplier_id,
                    "quantity": purchase_order.quantity,
                    "placed_minute": round(purchase_order.placed_minute, 6),
                    "promised_receipt_minute": round(
                        purchase_order.promised_receipt_minute,
                        6,
                    ),
                    "actual_receipt_minute": (
                        round(purchase_order.actual_receipt_minute, 6)
                        if purchase_order.actual_receipt_minute is not None
                        else None
                    ),
                    "unit_cost": purchase_order.unit_cost,
                    "total_committed_cost": purchase_order.total_committed_cost,
                    "status": purchase_order.status.value,
                }
                for purchase_order in purchase_orders
            ],
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
        backlog = [
            order
            for order in orders
            if order.status != OrderStatus.PENDING and order.remaining_quantity > 0
        ]
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
            "backlog_units": sum(order.remaining_quantity for order in backlog),
            "backlog_orders": len(backlog),
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
