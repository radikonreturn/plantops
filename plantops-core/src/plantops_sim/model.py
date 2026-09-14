from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class MachineState(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    STARVED = "STARVED"
    DOWN = "DOWN"


@dataclass(frozen=True)
class StageConfig:
    id: str
    name: str
    ideal_cycle_minutes: float
    cycle_jitter: float
    failure_probability: float = 0.0
    repair_min_minutes: float = 0.0
    repair_max_minutes: float = 0.0
    scrap_probability: float = 0.0


@dataclass(frozen=True)
class Scenario:
    raw_material_units: int
    shift_minutes: float
    stages: tuple[StageConfig, ...]
    buffer_capacities: dict[str, int]


@dataclass
class Buffer:
    id: str
    capacity: int | None
    units: list[int] = field(default_factory=list)

    def can_take(self) -> bool:
        return self.capacity is None or len(self.units) < self.capacity

    def put(self, unit_id: int) -> None:
        if not self.can_take():
            raise RuntimeError(f"Buffer {self.id} is full")
        self.units.append(unit_id)

    def get(self) -> int:
        if not self.units:
            raise RuntimeError(f"Buffer {self.id} is empty")
        return self.units.pop(0)

    @property
    def size(self) -> int:
        return len(self.units)


@dataclass
class Machine:
    config: StageConfig
    input_buffer: str
    output_buffer: str
    state: MachineState = MachineState.IDLE
    busy_unit: int | None = None
    run_minutes: float = 0.0
    down_minutes: float = 0.0
    processed_units: int = 0
    scrap_units: int = 0
    failures: int = 0


@dataclass(frozen=True)
class EventRecord:
    time: float
    kind: str
    machine_id: str | None = None
    unit_id: int | None = None
    detail: str = ""
