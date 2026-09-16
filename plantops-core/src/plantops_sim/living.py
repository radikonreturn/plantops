"""Bounded V3 shift state. All mutations run on the engine event/command path."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .engine import ProductionLineSimulation


@dataclass
class ShiftEvent:
    id: str
    minute: float
    end_minute: float
    kind: str
    title: str
    detail: str
    severity: str
    zone: str
    workspace: str
    state: Literal["scheduled", "active", "resolved", "expired"] = "scheduled"
    closed_minute: float | None = None
    affected_ids: tuple[str, ...] = ()


class LivingShift:
    def __init__(self, simulation: ProductionLineSimulation, primary_zone: str) -> None:
        self.simulation = simulation
        self.normal_minutes = simulation.scenario.shift_minutes
        self.overtime_authorized = False
        self.containment_available = primary_zone == "quality_01"
        self.containment_active = False
        self.inspected_units = 0
        self.inspection_minutes = 0.0
        self.captured_units = 0
        self.escaped_ids: set[int] = set()
        self.inspection_units: set[int] = set()
        self.expedited: dict[str, float] = {}
        self.receipt_times: dict[str, float] = {}
        self.receipt_event_ids: dict[str, int] = {}
        self.events: dict[str, ShiftEvent] = {}
        rng = simulation.rng.get("shift-events:v1")
        favored = ("supplier_delay" if primary_zone == "raw" else
                   "customer_escalation" if primary_zone == "dispatch" else
                   "quality_notice" if self.containment_available else "condition_risk")
        choices = ["supplier_delay", "customer_escalation", "operator_shortage", "condition_risk"]
        if self.containment_available:
            choices.append("quality_notice")
        kinds = [favored] + rng.sample([k for k in choices if k != favored], 2)
        for index, kind in enumerate(kinds):
            minute = float(45 + index * 115 + rng.randint(0, 40))
            zone = primary_zone if primary_zone in simulation.machines and primary_zone != "quality_01" else "cnc_01"
            title, detail, workspace = {
                "condition_risk": ("Equipment condition warning", "Health decreases by 18 points; service restores health. Risk remains until serviced or shift close.", "Maintenance"),
                "operator_shortage": ("Temporary operator shortage", "New cycles at this station take 40% longer for 60 minutes.", "Production Plan"),
                "supplier_delay": ("Supplier transport disruption", "Open receipts and orders placed during this 60-minute disruption gain 25 minutes of transit time once.", "Inventory"),
                "customer_escalation": ("Customer dispatch escalation", "An unfinished released order gains 15 priority points (capped at 100); earliest due still governs allocation.", "Orders"),
                "quality_notice": ("Quality containment notice", "Latent defect exposure rises from 6% to 12% of units passing normal inspection for 60 minutes.", "Quality"),
            }[kind]
            if kind == "supplier_delay":
                zone = "receiving"
            elif kind == "customer_escalation":
                zone = "dispatch"
            elif kind == "quality_notice":
                zone = "quality_01"
            event = ShiftEvent(f"SHIFT-{index + 1:02d}", minute, minute + 60,
                               kind, title, detail, "critical" if kind == "quality_notice" else "attention", zone, workspace)
            self.events[event.id] = event
            simulation._schedule(minute, "SHIFT_EVENT_START", event.id)
            simulation._schedule(event.end_minute, "SHIFT_EVENT_END", event.id)

    @property
    def end_minute(self) -> float:
        return self.normal_minutes + (60 if self.overtime_authorized else 0)

    @property
    def fatigue_active(self) -> bool:
        return self.overtime_authorized and self.normal_minutes <= self.simulation.clock < self.end_minute

    def require_open(self) -> None:
        from .engine import ShiftActionUnavailableError
        if self.simulation.clock >= self.end_minute:
            raise ShiftActionUnavailableError("Shift is closed; interventions are unavailable")

    def authorize_overtime(self) -> None:
        from .engine import ShiftActionUnavailableError
        self.require_open()
        if self.overtime_authorized:
            raise ShiftActionUnavailableError("Overtime already authorized once this shift")
        self.overtime_authorized = True
        self.simulation._schedule(self.normal_minutes, "OVERTIME_STARTED")
        self.simulation._record("OVERTIME_AUTHORIZED", detail="extension=60;labor_cost=600;failure_multiplier=1.2 during minutes 480–540 only")

    def activate_containment(self) -> None:
        from .engine import ShiftActionUnavailableError
        self.require_open()
        if not self.containment_available or self.containment_active:
            raise ShiftActionUnavailableError("Containment requires a quality-containment profile and can be activated only once")
        self.containment_active = True
        self.simulation._record("QUALITY_CONTAINMENT_ACTIVATED", detail="extra_cycle_minutes=0.6;inspection_cost_per_unit=2;latent_defects_isolated;source_risk_unchanged")

    def reschedule_receipt(self, po_id: str, minute: float) -> None:
        sim = self.simulation
        sim._cancel_scheduled_event(self.receipt_event_ids[po_id])
        self.receipt_times[po_id] = minute
        self.receipt_event_ids[po_id] = sim._schedule(minute, "MATERIAL_RECEIVED", po_id)

    def expedite(self, po_id: str) -> None:
        from .engine import ShiftActionUnavailableError, UnknownPurchaseOrderError
        sim = self.simulation
        po = sim.purchase_orders.get(po_id)
        if po is None:
            raise UnknownPurchaseOrderError(f"Purchase order '{po_id}' was not found")
        self.require_open()
        if po.status != "OPEN" or po_id in self.expedited:
            raise ShiftActionUnavailableError("Only an open, not previously expedited purchase order can be expedited")
        self.reschedule_receipt(po_id, sim.clock + (self.receipt_times[po_id] - sim.clock) / 2)
        self.expedited[po_id] = 120.0
        sim._record("PURCHASE_ORDER_EXPEDITED", detail=f"purchase_order_id={po_id};cost=120;expected_receipt_minute={self.receipt_times[po_id]:.6f}")

    def register_receipt(self, po_id: str, minute: float, event_id: int) -> None:
        self.receipt_times[po_id] = minute
        self.receipt_event_ids[po_id] = event_id
        for event in self.events.values():
            if event.kind == "supplier_delay" and event.state == "active" and self.simulation.clock < event.end_minute:
                self.delay_receipt(event, po_id)

    def delay_receipt(self, event: ShiftEvent, po_id: str) -> None:
        if po_id not in event.affected_ids:
            self.reschedule_receipt(po_id, self.receipt_times[po_id] + 25)
            event.affected_ids += (po_id,)
            self.simulation._record("SUPPLIER_RECEIPT_DELAYED", detail=f"event_id={event.id};purchase_order_id={po_id};delay=25")

    def handle_event(self, kind: str, event_id: str) -> None:
        sim = self.simulation
        event = self.events[event_id]
        if kind == "SHIFT_EVENT_START":
            event.state = "active"
            sim._record("SHIFT_EVENT_ACTIVE", detail=f"event_id={event.id};kind={event.kind};{event.detail}")
            if event.kind == "condition_risk":
                sim.machines[event.zone].health = max(0, sim.machines[event.zone].health - 18)
            elif event.kind == "supplier_delay":
                for po in sim.purchase_orders.values():
                    if po.status == "OPEN":
                        self.delay_receipt(event, po.id)
            elif event.kind == "customer_escalation":
                candidates = [o for o in sim.orders.values() if o.status != "PENDING" and o.remaining_quantity]
                if candidates:
                    order = min(candidates, key=lambda o: (o.due_minute, o.priority, o.id))
                    order.priority = min(100, order.priority + 15)
                    event.affected_ids = (order.id,)
                    sim._record("CUSTOMER_ESCALATED", detail=f"event_id={event.id};order_id={order.id};priority={order.priority}")
                else:
                    self.finish(event, "expired")
        elif event.state == "active" and event.kind in {"operator_shortage", "quality_notice"}:
            self.finish(event, "expired")
        elif event.state == "active" and event.kind == "supplier_delay" and not event.affected_ids:
            self.finish(event, "expired")
        self.reconcile()

    def finish(self, event: ShiftEvent, state: Literal["resolved", "expired"]) -> None:
        event.state = state
        event.closed_minute = self.simulation.clock
        self.simulation._record(f"SHIFT_EVENT_{state.upper()}", detail=f"event_id={event.id}")

    def reconcile(self) -> None:
        sim = self.simulation
        for event in self.events.values():
            if event.state != "active":
                continue
            resolved = (
                (event.kind == "condition_risk" and sim.machines[event.zone].health >= 99)
                or (event.kind == "customer_escalation" and bool(event.affected_ids)
                    and all(sim.orders[i].remaining_quantity == 0 for i in event.affected_ids))
                or (event.kind == "supplier_delay" and sim.clock >= event.end_minute and bool(event.affected_ids)
                    and all(sim.purchase_orders[i].status != "OPEN" for i in event.affected_ids))
            )
            if resolved:
                self.finish(event, "resolved")
            elif sim.clock >= self.end_minute:
                self.finish(event, "expired")

    def cycle_minutes(self, machine_id: str, unit_id: int, cycle: float) -> float:
        for event in self.events.values():
            if event.state == "active" and event.kind == "operator_shortage" and event.zone == machine_id:
                cycle *= 1.4
        if machine_id == "quality_01" and self.containment_active:
            self.inspection_units.add(unit_id)
            self.inspected_units += 1
            self.inspection_minutes += 0.6
            cycle += 0.6
        return cycle

    def latent_defect(self, machine_id: str, unit_id: int) -> bool:
        """Called only for units passing normal inspection; True isolates as scrap."""
        if machine_id != "quality_01" or not self.containment_available:
            return False
        risk = 0.12 if any(e.kind == "quality_notice" and e.state == "active" for e in self.events.values()) else 0.06
        defect = self.simulation.rng.get("quality:latent:v1").random() < risk
        inspected = unit_id in self.inspection_units
        self.inspection_units.discard(unit_id)
        if defect and inspected:
            self.captured_units += 1
            self.simulation._record("LATENT_DEFECT_CONTAINED", machine_id, unit_id)
            return True
        if defect:
            self.escaped_ids.add(unit_id)
            self.simulation._record("LATENT_DEFECT_RELEASED", machine_id, unit_id)
        return False

    def snapshot(self) -> dict[str, Any]:
        sim = self.simulation
        closed = sim.clock >= self.end_minute
        escapes = len(self.escaped_ids & sim.finished_goods.allocated_order_by_unit.keys())
        return {
            "shift_events": [asdict(e) for e in self.events.values()],
            "overtime": {"authorized": self.overtime_authorized, "extension_minutes": 60,
                         "normal_shift_minutes": self.normal_minutes, "labor_cost": 600 if self.overtime_authorized else 0,
                         "fatigue_active": self.fatigue_active, "failure_multiplier": 1.2,
                         "unavailable_reason": "Shift closed" if closed else "Already authorized" if self.overtime_authorized else None},
            "quality_containment": {"available": self.containment_available, "active": self.containment_active,
                "unavailable_reason": "Shift closed" if closed else "Already active" if self.containment_active else
                None if self.containment_available else "Requires a quality-containment profile",
                "inspected_units": self.inspected_units, "added_inspection_minutes": round(self.inspection_minutes, 3),
                "inspection_cost": self.inspected_units * 2, "captured_units": self.captured_units,
                "customer_escapes": escapes, "suspect_finished_units": len(self.escaped_ids) - escapes},
        }
