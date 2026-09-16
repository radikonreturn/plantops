from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite


class MachineState(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    STARVED = "STARVED"
    DOWN = "DOWN"
    PLANNED_MAINTENANCE = "PLANNED_MAINTENANCE"


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    LATE = "LATE"
    COMPLETED_ON_TIME = "COMPLETED_ON_TIME"
    COMPLETED_LATE = "COMPLETED_LATE"


class PurchaseOrderStatus(StrEnum):
    OPEN = "OPEN"
    RECEIVED_ON_TIME = "RECEIVED_ON_TIME"
    RECEIVED_LATE = "RECEIVED_LATE"


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
    health_loss_per_processed_unit: float = 0.0
    wear_based_failure_multiplier: float = 0.0
    preventive_maintenance_duration: float = 0.0
    preventive_maintenance_cost: float = 0.0
    initial_health: float = 100.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.initial_health, bool)
            or not isinstance(self.initial_health, (int, float))
            or not isfinite(self.initial_health)
            or not 0 <= self.initial_health <= 100
        ):
            raise ValueError("Initial machine health must be between 0 and 100")
        maintenance_fields = (
            ("health loss per processed unit", self.health_loss_per_processed_unit),
            ("wear-based failure multiplier", self.wear_based_failure_multiplier),
            ("preventive-maintenance duration", self.preventive_maintenance_duration),
            ("preventive-maintenance cost", self.preventive_maintenance_cost),
        )
        for field_name, value in maintenance_fields:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
            ):
                raise ValueError(
                    f"Stage {field_name} must be a finite, non-negative number"
                )


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
        if self.due_minute <= self.release_minute:
            raise ValueError("Order due minute must be after its release minute")


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
class SupplierConfig:
    id: str
    name: str
    min_lead_minutes: float
    max_lead_minutes: float
    late_probability: float
    max_delay_minutes: float
    unit_cost: float

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Supplier ID cannot be empty")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Supplier name cannot be empty")
        if (
            isinstance(self.min_lead_minutes, bool)
            or not isinstance(self.min_lead_minutes, (int, float))
            or not isfinite(self.min_lead_minutes)
            or self.min_lead_minutes <= 0
        ):
            raise ValueError("Supplier minimum lead minutes must be a positive number")
        if (
            isinstance(self.max_lead_minutes, bool)
            or not isinstance(self.max_lead_minutes, (int, float))
            or not isfinite(self.max_lead_minutes)
            or self.max_lead_minutes < self.min_lead_minutes
        ):
            raise ValueError(
                "Supplier maximum lead minutes must be at least the minimum lead minutes"
            )
        if (
            isinstance(self.late_probability, bool)
            or not isinstance(self.late_probability, (int, float))
            or not isfinite(self.late_probability)
            or not 0 <= self.late_probability <= 1
        ):
            raise ValueError("Supplier late probability must be between 0 and 1")
        if (
            isinstance(self.max_delay_minutes, bool)
            or not isinstance(self.max_delay_minutes, (int, float))
            or not isfinite(self.max_delay_minutes)
            or self.max_delay_minutes < 0
        ):
            raise ValueError("Supplier maximum delay minutes cannot be negative")
        if self.late_probability > 0 and self.max_delay_minutes == 0:
            raise ValueError(
                "Supplier maximum delay minutes must be positive when late deliveries are possible"
            )
        if (
            isinstance(self.unit_cost, bool)
            or not isinstance(self.unit_cost, (int, float))
            or not isfinite(self.unit_cost)
            or self.unit_cost < 0
        ):
            raise ValueError("Supplier unit cost cannot be negative")


@dataclass(frozen=True)
class Scenario:
    raw_material_units: int
    shift_minutes: float
    stages: tuple[StageConfig, ...]
    buffer_capacities: dict[str, int | None]
    orders: tuple[OrderConfig, ...] = ()
    urgent_order_rule: UrgentOrderRule | None = None
    suppliers: tuple[SupplierConfig, ...] = ()
    initial_wip: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for buffer_id, quantity in self.initial_wip:
            if (
                buffer_id in seen
                or buffer_id not in self.buffer_capacities
                or buffer_id in {"raw", "finished"}
            ):
                raise ValueError("Initial WIP must name unique inter-stage buffers")
            capacity = self.buffer_capacities[buffer_id]
            if type(quantity) is not int or quantity < 0 or (
                capacity is not None and quantity > capacity
            ):
                raise ValueError("Initial WIP must be a non-negative integer within capacity")
            seen.add(buffer_id)


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
class PurchaseOrderState:
    id: str
    supplier_id: str
    quantity: int
    placed_minute: float
    promised_receipt_minute: float
    unit_cost: float
    total_committed_cost: float
    actual_receipt_minute: float | None = None
    status: PurchaseOrderStatus = PurchaseOrderStatus.OPEN


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
    health: float = 100.0
    maintenance_count: int = 0
    planned_maintenance_minutes: float = 0.0
    active_maintenance_start_minute: float | None = None


@dataclass(frozen=True)
class EventRecord:
    time: float
    kind: str
    machine_id: str | None = None
    unit_id: int | None = None
    detail: str = ""
