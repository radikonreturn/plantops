"""Bounded V3 shift state. All mutations run on the engine event/command path."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    root_cause: str = ""
    operational_impact: str = ""

    start_minute: float = 0
    deadline_minute: float = 0
    choices: list[dict[str, Any]] = field(default_factory=list)
    selected_choice: str | None = None
    resolved_minute: float | None = None
    outcome: str | None = None
    expected: str = ""
    no_action: str = ""
    decision_cost: float = 0
    pressure: float = 1
    effect_until: float = 0
    baseline: dict[str, float] = field(default_factory=dict)
    impact: dict[str, float] = field(default_factory=dict)


class UnknownShiftDecisionError(LookupError):
    pass


class LivingShift:
    def __init__(self, simulation: ProductionLineSimulation, primary_zone: str, *, schedule_events: bool = True, difficulty: str = "normal") -> None:
        self.simulation = simulation
        self.normal_minutes = simulation.scenario.shift_minutes
        self.overtime_authorized = False
        self.profile_latent_risk = primary_zone == "quality_01"
        self.containment_available = self.profile_latent_risk
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
        self.difficulty = difficulty
        self.decision_cost = 0.0
        self.energy_cost = 0.0
        self.customer_value = 0
        self.objective: dict[str, Any] | None = None
        if schedule_events:
            self.schedule_decisions(primary_zone)

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
            raise ShiftActionUnavailableError("Containment requires a quality handover or detected wash-residue exposure and can be activated only once")
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
            if event.kind == "supplier_delay" and event.state != "scheduled" and self.simulation.clock < event.effect_until:
                self.delay_receipt(event, po_id)

    def delay_receipt(self, event: ShiftEvent, po_id: str) -> None:
        if po_id not in event.affected_ids:
            self.reschedule_receipt(po_id, self.receipt_times[po_id] + 25 * event.pressure * (0.5 if event.selected_choice == "freight" else 1))
            event.affected_ids += (po_id,)
            self.simulation._record("SUPPLIER_RECEIPT_DELAYED", detail=f"event_id={event.id};purchase_order_id={po_id};delay={25 * event.pressure * (0.5 if event.selected_choice == 'freight' else 1):g}")

    def handle_event(self, kind: str, event_id: str) -> None:
        event = self.events[event_id]
        if kind == "SHIFT_EVENT_START" and event.state == "scheduled":
            self.start_decision(event)
        elif kind == "SHIFT_DECISION_DEADLINE" and event.state == "active" and event.choices:
            self.apply_decision(event, None)
        self.reconcile()

    def finish(self, event: ShiftEvent, state: Literal["resolved", "expired"]) -> None:
        if event.state not in {"active", "scheduled"}:
            return
        if event.kind == "operator_shortage" and state == "resolved" and event.selected_choice not in {"rebalance", "cover"}:
            event.effect_until = self.simulation.clock
        if event.choices and state == "resolved" and event.outcome is None:
            event.selected_choice = "existing_action"
            event.outcome = "Existing service resolved the operational pressure."
        event.state = state
        event.resolved_minute = self.simulation.clock
        event.closed_minute = self.simulation.clock
        self.simulation._record(f"SHIFT_EVENT_{state.upper()}", machine_id=event.zone if event.zone in self.simulation.machines else None, detail=f"event_id={event.id};{event.title};{state}")

    def reconcile(self) -> None:
        sim = self.simulation
        for event in self.events.values():
            if event.state != "active":
                continue
            if event.choices or event.kind == "management_objective":
                if sim.clock >= self.end_minute and event.kind == "management_objective":
                    self.finish(event, "resolved")
                    event.outcome = "Objective reviewed against actual shift results."
                continue
            if sim.clock >= self.end_minute:
                self.finish(event, "expired")

    def cycle_minutes(self, machine_id: str, unit_id: int, cycle: float) -> float:
        for event in self.events.values():
            if event.kind == "operator_shortage" and event.zone == machine_id and self.effect_active(event):
                cycle *= 1 + .4 * event.pressure
            if event.kind == "energy_window" and self.effect_active(event) and event.selected_choice != "reserve":
                cost = round(.8 * event.pressure, 2)
                self.energy_cost = round(self.energy_cost + cost, 2)
                self.simulation._record("ENERGY_SURCHARGE", machine_id, unit_id, f"event_id={event.id};cost={cost}")
            if event.kind == "operator_shortage" and machine_id == "test_01" and self.effect_active(event) and event.selected_choice == "rebalance":
                cycle *= 1.15
        if machine_id == "quality_01" and self.containment_active:
            self.inspection_units.add(unit_id)
            self.inspected_units += 1
            self.inspection_minutes += 0.6
            cycle += 0.6
        return cycle

    def latent_defect(self, machine_id: str, unit_id: int) -> bool:
        """Called only for units passing normal inspection; True isolates as scrap."""
        if machine_id != "quality_01" or not (self.profile_latent_risk or any(e.kind == "quality_notice" and self.effect_active(e) for e in self.events.values())):
            return False
        risk = max([.06 if self.profile_latent_risk else 0] + [.12 * e.pressure for e in self.events.values() if e.kind == "quality_notice" and self.effect_active(e)])
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
            "shift_events": [self.event_snapshot(e) for e in self.events.values()],
            "management_objective": self.objective_snapshot(),
            "decision_review": self.decision_review(),
            "overtime": {"authorized": self.overtime_authorized, "extension_minutes": 60,
                         "normal_shift_minutes": self.normal_minutes, "labor_cost": 600 if self.overtime_authorized else 0,
                         "fatigue_active": self.fatigue_active, "failure_multiplier": 1.2,
                         "unavailable_reason": "Shift closed" if closed else "Already authorized" if self.overtime_authorized else None},
            "quality_containment": {"available": self.containment_available, "active": self.containment_active,
                "unavailable_reason": "Shift closed" if closed else "Already active" if self.containment_active else
                None if self.containment_available else "Requires a quality handover or detected wash-residue exposure",
                "inspected_units": self.inspected_units, "added_inspection_minutes": round(self.inspection_minutes, 3),
                "inspection_cost": self.inspected_units * 2, "captured_units": self.captured_units,
                "customer_escapes": escapes, "suspect_finished_units": len(self.escaped_ids) - escapes},
        }

    def schedule_decisions(self, primary_zone: str) -> None:
        """Use only the existing dedicated schedule stream; bind live targets at start."""
        sim = self.simulation
        rng = sim.rng.get("shift-events:v1")
        count, window, pressure = {"easy": (3, 45, .7), "normal": (4, 30, 1.0), "hard": (6, 18, 1.4)}[self.difficulty]
        primary_family = {"raw": "supplier_delay", "dispatch": "customer_escalation", "quality_01": "quality_notice", "assembly_01": "operator_shortage"}.get(primary_zone, "condition_risk")
        families = ["supplier_delay", "customer_escalation", "operator_shortage", "condition_risk", "quality_notice", "energy_window"]
        candidates = [k for k in families if k != primary_family]
        # A different equipment target complements a machine-led handover on hard shifts.
        if count > len(candidates):
            candidates.append(primary_family)
        kinds = rng.sample(candidates, count)
        if rng.random() < .65:
            kinds[-1] = "management_objective"
        machine_ids = [mid for mid in sim.machines if mid not in {primary_zone, "quality_01"}]
        for index, kind in enumerate(kinds):
            minute = float(45 + index * (50 if self.difficulty == "hard" else 85) + rng.randint(0, 20))
            zone = rng.choice(machine_ids) if kind == "condition_risk" else {
                "supplier_delay": "receiving", "customer_escalation": "dispatch", "operator_shortage": "assembly_01",
                "quality_notice": "quality_01", "energy_window": "plant", "management_objective": "dispatch",
            }[kind]
            title, detail, workspace, no_action = EVENT_COPY[kind]
            event = ShiftEvent(f"SHIFT-{index + 1:02d}", minute, minute + window + 60,
                               kind, title, detail, "attention", zone, workspace,
                               start_minute=minute, deadline_minute=minute + window,
                               pressure=pressure, effect_until=minute + window + 60,
                               no_action=no_action, root_cause=title, operational_impact=detail)
            if kind != "management_objective":
                event.choices = [dict(id=cid, label=label, expected=expected,
                                      cost=round(cost * pressure, 2))
                                 for cid, label, expected, cost in CHOICES[kind]]
            self.events[event.id] = event
            sim._schedule(minute, "SHIFT_EVENT_START", event.id)
            sim._schedule(event.deadline_minute, "SHIFT_DECISION_DEADLINE", event.id)
            sim._schedule(event.end_minute, "SHIFT_EVENT_END", event.id)

    def effect_active(self, event: ShiftEvent) -> bool:
        return event.state != "scheduled" and event.minute <= self.simulation.clock < event.effect_until

    def observations(self) -> dict[str, float]:
        sim = self.simulation
        return {"delivered": sum(o.fulfilled_quantity for o in sim.orders.values()),
                "scrap": sum(m.scrap_units for m in sim.machines.values()),
                "failures": sum(m.failures for m in sim.machines.values())}

    def start_decision(self, event: ShiftEvent) -> None:
        sim = self.simulation
        event.state = "active"
        event.baseline = self.observations()
        if event.zone in sim.machines:
            event.affected_ids = (event.zone,)
        if event.kind in {"customer_escalation", "management_objective"}:
            orders = sorted((o for o in sim.orders.values() if o.remaining_quantity and o.status != "PENDING"),
                            key=lambda o: (o.due_minute, -o.priority, o.id))
            if orders:
                event.affected_ids = (orders[0].id,)
            elif event.kind == "customer_escalation":
                # No fictional order: the current line instead receives a real energy offer.
                event.kind = "energy_window"
                event.title, event.detail, event.workspace, event.no_action = EVENT_COPY[event.kind]
                event.zone = "plant"
                event.choices = [dict(id=cid, label=label, expected=expected, cost=round(cost * event.pressure, 2))
                                 for cid, label, expected, cost in CHOICES[event.kind]]
            if event.kind == "management_objective":
                target = event.affected_ids[0] if event.affected_ids else "good_production"
                self.objective = {"event_id": event.id, "target_id": target,
                                  "kind": "protect_order" if event.affected_ids else "throughput",
                                  "start_minute": sim.clock,
                                  "target": 1 if event.affected_ids else sim.finished_goods.size + 20}
                sim._record("MANAGEMENT_OBJECTIVE_CHANGED", detail=f"event_id={event.id};target={target}")
        if event.kind == "condition_risk":
            self.change_condition(event, -18 * event.pressure)
        elif event.kind == "supplier_delay":
            event.affected_ids = tuple(sim.suppliers)
            for po in sim.purchase_orders.values():
                if po.status == "OPEN":
                    self.delay_receipt(event, po.id)
        elif event.kind == "quality_notice":
            self.containment_available = True
        sim._record("SHIFT_EVENT_ACTIVE", machine_id=event.zone if event.zone in sim.machines else None,
                    detail=f"event_id={event.id};kind={event.kind};{event.detail}")

    def change_condition(self, event: ShiftEvent, health_delta: float) -> None:
        sim = self.simulation
        machine = sim.machines[event.zone]
        machine.health = max(0, min(100, machine.health + health_delta))
        if sim.equipment and event.zone in sim.equipment.conditions:
            condition = sim.equipment.conditions[event.zone]
            condition.burden = max(0, min(100, condition.burden - health_delta))

    def choice_unavailable(self, event: ShiftEvent, choice_id: str) -> str | None:
        sim = self.simulation
        if event.state != "active" or sim.clock >= event.deadline_minute or sim.clock >= self.end_minute:
            return "Decision window is closed."
        if choice_id == "service":
            if sim.equipment and event.zone in sim.equipment.conditions:
                return sim.equipment.unavailable(event.zone)
            if sim.machines[event.zone].state not in {"IDLE", "STARVED", "BLOCKED"}:
                return "Wait for an idle machine or use external support."
        if choice_id in {"protect", "overtime"}:
            order = sim.orders.get(event.affected_ids[0]) if event.affected_ids else None
            if not order or not order.remaining_quantity:
                return "The referenced order is already complete."
            if choice_id == "overtime" and self.overtime_authorized:
                return "Already authorized"
        if choice_id == "contain" and self.containment_active:
            return "Already active"
        return None

    def decide(self, event_id: str, choice_id: str) -> None:
        from .engine import ShiftActionUnavailableError
        event = self.events.get(event_id)
        if event is None:
            raise UnknownShiftDecisionError("Unknown shift event")
        if not any(c["id"] == choice_id for c in event.choices):
            raise UnknownShiftDecisionError("Unknown event choice")
        self.require_open()
        reason = self.choice_unavailable(event, choice_id)
        if reason:
            raise ShiftActionUnavailableError(reason)
        self.apply_decision(event, choice_id)

    def apply_decision(self, event: ShiftEvent, choice_id: str | None) -> None:
        """Only called after validation under the session lock, or by its deadline event."""
        if event.state != "active":
            return
        sim = self.simulation
        choice = next((c for c in event.choices if c["id"] == choice_id), None)
        before = self.observations()
        cost = choice["cost"] if choice else 0
        if event.kind == "condition_risk":
            if choice_id == "service":
                if sim.equipment and event.zone in sim.equipment.conditions:
                    from .equipment import SPECS
                    cost = SPECS[event.zone].cost
                    sim.equipment.request(event.zone, SPECS[event.zone].action)
                else:
                    cost = sim.preventive_maintenance_cost(event.zone)
                    sim.start_preventive_maintenance(event.zone)
                    self.decision_cost += cost
            elif choice_id == "external":
                self.change_condition(event, 25 * event.pressure)
            else:
                self.change_condition(event, -6 * event.pressure)
        elif event.kind == "operator_shortage":
            if choice_id == "cover":
                event.effect_until = sim.clock
            elif choice_id == "rebalance":
                event.pressure *= .5
                # Cross-training moves some pressure to testing for the same window.
                event.impact["test_cycle_multiplier"] = 1.15
            else:
                event.pressure *= 1.25
        elif event.kind == "supplier_delay" and choice_id == "freight":
            for po_id in event.affected_ids:
                po = sim.purchase_orders.get(po_id)
                if po and po.status == "OPEN":
                    self.reschedule_receipt(po_id, sim.clock + (self.receipt_times[po_id] - sim.clock) / 2)
        elif event.kind == "supplier_delay":
            for po_id in event.affected_ids:
                po = sim.purchase_orders.get(po_id)
                if po and po.status == "OPEN":
                    self.reschedule_receipt(po_id, self.receipt_times[po_id] + 5 * event.pressure)
            event.pressure *= 1.2
        elif event.kind == "energy_window" and choice_id != "reserve":
            event.pressure *= 1.1
        elif event.kind == "customer_escalation":
            if choice_id in {"protect", "overtime"}:
                if choice_id == "overtime":
                    self.authorize_overtime()
                    cost = 600
                sim.reprioritize_order(event.affected_ids[0], 100)
                self.customer_value += 5
            else:
                self.customer_value -= 5
        elif event.kind == "quality_notice":
            if choice_id == "contain":
                self.activate_containment()
            else:
                event.pressure *= 1.25
        # These actions already book their own normal cost category.
        if choice_id not in {"service", "overtime"}:
            self.decision_cost += cost
        event.decision_cost = cost
        event.selected_choice = choice_id
        event.expected = choice["expected"] if choice else event.no_action
        event.outcome = "Decision accepted; effects committed." if choice else "No intervention selected; default consequence applied."
        event.impact.update({f"immediate_{key}": value - before[key] for key, value in self.observations().items()})
        self.finish(event, "resolved" if choice else "expired")
        sim._record("SHIFT_DECISION_ACCEPTED" if choice else "SHIFT_DECISION_EXPIRED",
                    machine_id=event.zone if event.zone in sim.machines else None,
                    detail=f"event_id={event.id};choice={choice_id or 'none'};cost={cost:g};{event.expected}")

    def event_snapshot(self, event: ShiftEvent) -> dict[str, Any]:
        result = asdict(event)
        for choice in result["choices"]:
            choice["unavailable_reason"] = self.choice_unavailable(event, choice["id"])
            if choice["id"] == "service":
                from .equipment import SPECS
                choice["cost"] = SPECS[event.zone].cost if event.zone in SPECS else self.simulation.preventive_maintenance_cost(event.zone)
            elif choice["id"] == "overtime":
                choice["cost"] = 600
        return result

    def objective_snapshot(self) -> dict[str, Any] | None:
        if self.objective is None:
            return None
        result = dict(self.objective)
        if result["kind"] == "protect_order":
            order = self.simulation.orders[result["target_id"]]
            achieved = order.status == "COMPLETED_ON_TIME"
        else:
            achieved = self.simulation.finished_goods.size >= result["target"]
        result["status"] = "achieved" if achieved else "missed" if self.simulation.clock >= self.end_minute else "open"
        return result

    def decision_review(self) -> dict[str, Any]:
        events = [e for e in self.events.values() if e.id.startswith("SHIFT-") and e.state != "scheduled"]
        return {"received": len(events), "answered": sum(e.selected_choice is not None for e in events),
                "ignored": sum(e.state == "expired" and bool(e.choices) for e in events),
                "decision_cost": round(sum(e.decision_cost for e in events), 2),
                "energy_cost": self.energy_cost, "customer_value": self.customer_value,
                "objective": self.objective_snapshot(),
                "observed": self.observations(),
                "note": "Delivery, quality and equipment totals are observed results, not isolated causal estimates."}


EVENT_COPY = {
    "condition_risk": ("Equipment condition warning", "A secondary station is deteriorating. Service costs capacity; continuing exposes health and quality.", "Maintenance", "Without intervention, health falls further and equipment burden increases."),
    "supplier_delay": ("Supplier transport disruption", "Transit disruption affects open and newly placed receipts during the window. Priority freight trades cash for shorter remaining transit.", "Inventory", "Without intervention, open receipts gain additional delay and disruption pressure increases."),
    "operator_shortage": ("Temporary operator shortage", "Assembly capacity is reduced. Cover costs money; sharing staff also slows testing.", "Production Plan", "Without intervention, assembly capacity falls further until the pressure window ends."),
    "customer_escalation": ("Customer priority request", "The manager requests priority for the referenced active order. Allocation still follows due dates before priority.", "Orders", "Without intervention, the request is declined and customer commitment value falls."),
    "quality_notice": ("Quality containment request", "A suspect lot raises latent defect exposure. Added inspection protects new releases but consumes capacity and money.", "Quality", "Without intervention, latent defect exposure rises for the rest of the window."),
    "energy_window": ("Energy-price window", "New machine cycles incur an energy surcharge during this window. A fixed-price reservation may cost more if production stops.", "Production Plan", "Without intervention, the variable cycle surcharge rises by 10% until the window ends."),
    "management_objective": ("Manager objective update", "Protect the referenced order on time; if no active order remains, increase good production by the stated target. The manager will review actual results without changing allocation automatically.", "Office / Inbox", ""),
}
CHOICES = {
    "condition_risk": [
        ("service", "Request planned service", "Service restores health after completion; the stop may expose delivery. Existing suspect WIP remains.", 0),
        ("external", "Call external support", "External support restores some health and condition immediately at a premium; it does not complete orders or remove existing defects.", 300),
        ("monitor", "Continue and monitor", "Keep capacity now; health falls further and breakdown exposure remains.", 0)],
    "supplier_delay": [
        ("freight", "Reserve priority freight", "Halve remaining transit for affected open receipts and halve disruption added to new receipts. Later disruptions can still delay arrival.", 160),
        ("standard", "Keep standard freight", "Preserve cash; open receipts gain additional delay and disruption pressure increases.", 0)],
    "operator_shortage": [
        ("cover", "Hire temporary cover", "Remove the temporary assembly slowdown immediately; base machine condition is unchanged.", 180),
        ("rebalance", "Share testing staff", "Halve assembly staffing pressure but slow new testing cycles by 15% until the window ends.", 40)],
    "customer_escalation": [
        ("protect", "Protect this customer", "Set priority to 100 and accept the customer commitment; same-deadline orders may lose allocation. Delivery is not guaranteed.", 0),
        ("overtime", "Protect with overtime", "Set priority to 100 and add 60 production minutes for 600 labor cost; overtime fatigue increases failure exposure.", 600),
        ("decline", "Decline the request", "Keep the production plan; customer commitment value decreases by five.", 0)],
    "quality_notice": [
        ("contain", "Activate added inspection", "Inspect new quality cycles for 0.6 extra minutes and 2 cost per unit; already released units are unchanged.", 0),
        ("sample", "Continue normal sampling", "Preserve inspection capacity; latent exposure increases for the rest of the window.", 0)],
    "energy_window": [
        ("reserve", "Reserve fixed-price energy", "Pay the fixed reservation now; no further cycle surcharge in this window, even if the line stops.", 90),
        ("spot", "Pay variable energy", "No fixed charge; the variable cycle surcharge rises by 10% until the window ends.", 0)],
}
