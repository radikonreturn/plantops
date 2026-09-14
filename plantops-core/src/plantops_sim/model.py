from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum


class MachineState(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    STARVED = "STARVED"
    DOWN = "DOWN"


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    LATE = "LATE"
    COMPLETED_ON_TIME = "COMPLETED_ON_TIME"
    COMPLETED_LATE = "COMPLETED_LATE"


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
class OrderConfig:
    id: str
    quantity: int
    release_minute: float
    due_minute: float
    priority: int

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Order ID cannot be empty")
        if self.quantity <= 0:
            raise ValueError("Order quantity must be greater than zero")
        if self.release_minute < 0:
            raise ValueError("Order release minute cannot be negative")
        if self.due_minute < 0:
            raise ValueError("Order due minute cannot be negative")


@dataclass(frozen=True)
class UrgentOrderRule:
    id: str
    min_arrival_minute: int
    max_arrival_minute: int
    min_quantity: int
    max_quantity: int
    lead_time_minutes: float
    priority: int

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Urgent order ID cannot be empty")
        if self.min_arrival_minute < 0:
            raise ValueError("Urgent order arrival minute cannot be negative")
        if self.max_arrival_minute < self.min_arrival_minute:
            raise ValueError("Urgent order arrival range is invalid")
        if self.min_quantity <= 0 or self.max_quantity < self.min_quantity:
            raise ValueError("Urgent order quantity range is invalid")
        if self.lead_time_minutes <= 0:
            raise ValueError("Urgent order lead time must be greater than zero")


@dataclass(frozen=True)
class Scenario:
    raw_material_units: int
    shift_minutes: float
    stages: tuple[StageConfig, ...]
    buffer_capacities: dict[str, int | None]
    orders: tuple[OrderConfig, ...] = ()
    urgent_order_rule: UrgentOrderRule | None = None


@dataclass
class OrderState:
    id: str
    requested_quantity: int
    release_minute: float
    due_minute: float
    priority: int
    fulfilled_quantity: int = 0
    on_time_fulfilled_quantity: int = 0
    late_fulfilled_quantity: int = 0
    status: OrderStatus = OrderStatus.PENDING
    due_reached: bool = False
    was_late: bool = False

    @classmethod
    def from_config(cls, config: OrderConfig) -> OrderState:
        return cls(
            id=config.id,
            requested_quantity=config.quantity,
            release_minute=config.release_minute,
            due_minute=config.due_minute,
            priority=config.priority,
        )

    @property
    def remaining_quantity(self) -> int:
        return self.requested_quantity - self.fulfilled_quantity


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
class FinishedGoodsInventory(Buffer):
    available_unit_ids: deque[int] = field(default_factory=deque)
    allocated_order_by_unit: dict[int, str] = field(default_factory=dict)

    def put(self, unit_id: int) -> None:
        if unit_id in self.units:
            raise RuntimeError(f"Finished-good unit {unit_id} was received twice")
        super().put(unit_id)
        self.available_unit_ids.append(unit_id)

    def allocate_next(self, order_id: str) -> int:
        if not self.available_unit_ids:
            raise RuntimeError("No finished goods are available for allocation")
        unit_id = self.available_unit_ids.popleft()
        if unit_id in self.allocated_order_by_unit:
            raise RuntimeError(f"Finished-good unit {unit_id} was allocated twice")
        self.allocated_order_by_unit[unit_id] = order_id
        return unit_id

    @property
    def available_size(self) -> int:
        return len(self.available_unit_ids)

    @property
    def allocated_size(self) -> int:
        return len(self.allocated_order_by_unit)


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
