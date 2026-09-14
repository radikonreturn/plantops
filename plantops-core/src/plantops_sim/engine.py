from __future__ import annotations

import hashlib
import heapq
import random
from collections import Counter
from dataclasses import asdict
from typing import Any

from .model import Buffer, EventRecord, Machine, MachineState, Scenario


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
        self._events: list[tuple[float, int, str, str | None, int | None]] = []
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
        self._record("SIMULATION_STARTED", detail=f"seed={seed}")

    def _record(self, kind: str, machine_id: str | None = None, unit_id: int | None = None, detail: str = "") -> None:
        self.event_log.append(EventRecord(round(self.clock, 6), kind, machine_id, unit_id, detail))

    def _schedule(self, time: float, kind: str, machine_id: str | None = None, unit_id: int | None = None) -> None:
        self._sequence += 1
        heapq.heappush(self._events, (time, self._sequence, kind, machine_id, unit_id))

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
        if machine.config.failure_probability and self.rng.get(f"failure:{machine.config.id}").random() < machine.config.failure_probability:
            machine.state = MachineState.DOWN
            machine.failures += 1
            repair = self.rng.get(f"repair:{machine.config.id}").uniform(
                machine.config.repair_min_minutes, machine.config.repair_max_minutes
            )
            self._record("MACHINE_FAILED", machine.config.id, detail=f"repair_eta={repair:.2f}")
            self._schedule(self.clock + repair, "REPAIR_COMPLETED", machine.config.id)

    def _repair_machine(self, machine: Machine) -> None:
        if machine.state != MachineState.DOWN:
            return
        failure = next(event for event in reversed(self.event_log) if event.kind == "MACHINE_FAILED" and event.machine_id == machine.config.id)
        machine.down_minutes += self.clock - failure.time
        machine.state = MachineState.IDLE
        self._record("REPAIR_COMPLETED", machine.config.id)

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
            time, _, kind, machine_id, unit_id = heapq.heappop(self._events)
            self.clock = time
            machine = self.machines[machine_id] if machine_id else None
            if kind == "PROCESS_COMPLETED":
                assert machine is not None and unit_id is not None
                self._complete_process(machine, unit_id)
            elif kind == "REPAIR_COMPLETED":
                assert machine is not None
                self._repair_machine(machine)
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
        }

    def digest(self) -> str:
        rows = [asdict(event) for event in self.event_log]
        return hashlib.sha256(repr(rows).encode()).hexdigest()
