"""V4 equipment conditions, unit provenance and boundary-safe service commands."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .model import MachineState

if TYPE_CHECKING:
    from .engine import ProductionLineSimulation


@dataclass(frozen=True)
class EquipmentSpec:
    label: str
    fault: str
    action: str
    action_label: str
    duration: float
    cost: float
    cost_category: str


# Condition is a burden (0 best, 100 worst), separate from mechanical health.
SPECS = {
    "laser_01": EquipmentSpec(
        "Optical contamination", "lens contamination / assist-gas instability",
        "clean-lens", "Clean lens / purge gas", 8, 85, "lens_gas_cleaning"),
    "wash_01": EquipmentSpec(
        "Bath / filter burden", "filter differential above control limit",
        "service-wash", "Replace filter / replenish chemical", 12, 110,
        "chemical_filter_service"),
    "assembly_01": EquipmentSpec(
        "Tooling / staffing burden", "torque tool verification overdue",
        "assign-support", "Assign cross-trained operator", 6, 95, "support_labor"),
    "test_01": EquipmentSpec(
        "Calibration drift", "calibration drift suspected",
        "recalibrate-tester", "Recalibrate tester", 15, 160, "tester_calibration"),
    "quality_01": EquipmentSpec(
        "Inspection load", "inspection queue exceeds release capacity",
        "", "", 0, 0, ""),
}


@dataclass
class Condition:
    burden: float
    wear: float
    rework: int = 0
    catches: int = 0
    source_rejects: int = 0
    pending: bool = False
    active: bool = False
    costs: float = 0.0
    warning_id: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


class EquipmentSystems:
    def __init__(self, simulation: ProductionLineSimulation) -> None:
        self.sim = simulation
        self.conditions: dict[str, Condition] = {}
        self.defects: dict[int, str] = {}
        self.retesting: set[int] = set()
        self.escaped_ids: set[int] = set()
        for mid in SPECS:
            machine = simulation.machines[mid]
            rng = simulation.rng.get(f"machine:{mid.split('_')[0]}")
            burden = 100 - machine.health + rng.uniform(0, 5)
            if mid == "quality_01" and machine.config.scrap_probability > .05:
                burden = 65
            self.conditions[mid] = Condition(burden, rng.uniform(.035, .16))

    def pressure(self, mid: str) -> float:
        condition = self.conditions[mid]
        if mid == "quality_01":
            machine = self.sim.machines[mid]
            queue = self.sim.buffers[machine.input_buffer]
            return min(100, condition.burden + queue.size * 2)
        return condition.burden

    def multiplier(self, mid: str) -> float:
        if mid not in self.conditions:
            return 1.0
        p = max(0, self.pressure(mid) - 25) / 75
        return 1 + p * {"laser_01": 1.3, "wash_01": .3,
                        "assembly_01": 1.8, "test_01": .5, "quality_01": 2.0}[mid]

    def risk(self, mid: str) -> float:
        p = max(0, self.pressure(mid) - 25) / 75
        return p * {"laser_01": .16, "wash_01": .4,
                    "assembly_01": .22, "test_01": .3, "quality_01": .45}[mid]

    def reconcile(self) -> None:
        from .living import ShiftEvent
        sim = self.sim
        if not sim.living:
            return
        for mid, condition in self.conditions.items():
            if self.pressure(mid) >= 45 and condition.warning_id is None and sim.clock < sim.living.end_minute:
                eid = f"EQUIPMENT-{mid}-{len(condition.history)}-{sim._sequence}"
                condition.warning_id = eid
                impact = self.impact(mid)
                event = ShiftEvent(eid, sim.clock, sim.living.end_minute,
                                   "equipment_condition", f"{mid.replace('_', '-').upper()}: {SPECS[mid].fault}",
                                   impact, "attention", mid,
                                   "Quality" if mid in {"wash_01", "test_01", "quality_01"} else "Maintenance",
                                   state="active", affected_ids=(mid,),
                                   root_cause=SPECS[mid].fault, operational_impact=impact)
                sim.living.events[eid] = event
                sim._record("EQUIPMENT_WARNING", mid, detail=f"{event.title};{impact}")
            if condition.warning_id and self.pressure(mid) < 45:
                event = sim.living.events[condition.warning_id]
                if event.state == "active":
                    sim.living.finish(event, "resolved")
                condition.warning_id = None

    def impact(self, mid: str) -> str:
        return {
            "laser_01": "Slower cutting; contaminated optics increase source scrap.",
            "wash_01": "Residue travels with parts; downstream inspection or containment must catch it.",
            "assembly_01": "Reduced station capacity; torque verification adds rework time.",
            "test_01": "False failures add retests; drift reduces detection of residue defects.",
            "quality_01": "Release capacity falls; overloaded sampling can miss upstream defects.",
        }[mid]

    def unavailable(self, mid: str) -> str | None:
        sim = self.sim
        if mid not in self.conditions or not SPECS[mid].action:
            return "Use spindle maintenance or quality containment for this asset"
        c = self.conditions[mid]
        if sim.living and sim.clock >= sim.living.end_minute:
            return "Shift closed"
        if c.pending or c.active:
            return "Service already queued or in progress"
        if sim.machines[mid].state in {MachineState.DOWN, MachineState.PLANNED_MAINTENANCE}:
            return "Complete the current repair or maintenance first"
        staffing_shortage = mid == "assembly_01" and sim.living and any(
            e.kind == "operator_shortage" and e.zone == mid and e.state == "active"
            for e in sim.living.events.values()
        )
        if c.burden < 25 and not staffing_shortage:
            return "Condition is within control limits"
        return None

    def request(self, machine_id: str, action: str) -> None:
        from .engine import ShiftActionUnavailableError
        machine = self.sim._resolve_machine(machine_id)
        mid = machine.config.id
        if mid not in SPECS or action != SPECS[mid].action or not action:
            raise ShiftActionUnavailableError("Action is not supported by this asset")
        reason = self.unavailable(mid)
        if reason:
            raise ShiftActionUnavailableError(reason)
        c = self.conditions[mid]
        c.pending = True
        c.costs += SPECS[mid].cost
        c.history.append({"action": action, "requested_minute": self.sim.clock,
                          "started_minute": None, "completed_minute": None,
                          "cost": SPECS[mid].cost})
        self.sim._record("EQUIPMENT_SERVICE_REQUESTED", mid,
                         detail=f"{SPECS[mid].action_label} requested: {SPECS[mid].cost:g} cost; finish current unit before {SPECS[mid].duration:g}-minute stop")
        if machine.state != MachineState.RUNNING:
            self.start(mid)

    def start(self, mid: str) -> bool:
        c = self.conditions.get(mid)
        if c is None or not c.pending:
            return False
        machine = self.sim.machines[mid]
        c.pending, c.active = False, True
        c.history[-1]["started_minute"] = self.sim.clock
        machine.state = MachineState.PLANNED_MAINTENANCE
        machine.active_maintenance_start_minute = self.sim.clock
        self.sim._record("EQUIPMENT_SERVICE_STARTED", mid, detail=f"{SPECS[mid].action_label}: production stopped for {SPECS[mid].duration:g} minutes")
        self.sim._schedule(self.sim.clock + SPECS[mid].duration, "EQUIPMENT_SERVICE_COMPLETED", mid)
        return True

    def restore(self, mid: str) -> None:
        c = self.conditions.get(mid)
        if c:
            c.burden = 5
        if mid == "assembly_01" and self.sim.living:
            for event in self.sim.living.events.values():
                if event.kind == "operator_shortage" and event.zone == mid and event.state == "active":
                    self.sim.living.finish(event, "resolved")

    def complete_service(self, mid: str) -> None:
        c = self.conditions[mid]
        machine = self.sim.machines[mid]
        c.active = False
        c.history[-1]["completed_minute"] = self.sim.clock
        machine.planned_maintenance_minutes += SPECS[mid].duration
        machine.active_maintenance_start_minute = None
        machine.maintenance_count += 1
        machine.health = 100
        machine.state = MachineState.IDLE
        self.restore(mid)
        self.sim._record("EQUIPMENT_SERVICE_COMPLETED", mid, detail=f"{SPECS[mid].action_label} complete: condition restored; normal cycles resume")

    def retest(self, mid: str, unit_id: int) -> bool:
        if mid not in {"assembly_01", "test_01"}:
            return False
        if unit_id in self.retesting:
            self.retesting.remove(unit_id)
            return False
        machine = self.sim.machines[mid]
        if machine.config.failure_probability and self.sim.rng.get(f"machine:{mid.split('_')[0]}:rework").random() < self.risk(mid):
            self.retesting.add(unit_id)
            self.conditions[mid].rework += 1
            self.sim._record("EQUIPMENT_REWORK", mid, unit_id, "torque verification" if mid == "assembly_01" else "false failure; fixture retest")
            self.sim._schedule(self.sim.clock + (1.2 if mid == "assembly_01" else 2.5), "PROCESS_COMPLETED", mid, unit_id)
            return True
        return False

    def process(self, mid: str, unit_id: int, rejected: bool) -> bool:
        sim = self.sim
        c = self.conditions.get(mid)
        if not c:
            return rejected
        c.burden = min(100, c.burden + c.wear)
        rng = sim.rng.get(f"machine:{mid.split('_')[0]}:quality")
        enabled = sim.machines[mid].config.failure_probability > 0
        if not rejected and mid == "laser_01" and enabled and rng.random() < self.risk(mid):
            rejected = True
            c.source_rejects += 1
            sim._record("EQUIPMENT_SOURCE_REJECT", mid, unit_id, "contaminated optics; cut edge rejected")
        if not rejected and mid == "wash_01" and enabled and rng.random() < self.risk(mid):
            self.defects[unit_id] = mid
            sim._record("EQUIPMENT_DEFECT_CREATED", mid, unit_id, "chemical residue; downstream quality exposure")
            if sim.living:
                sim.living.containment_available = True
        if not rejected and mid == "test_01" and unit_id in self.defects:
            # A detected residue defect is scrapped; false failures consume retest time.
            if rng.random() < .9 - self.risk(mid) * 2:
                c.catches += 1
                del self.defects[unit_id]
                sim._record("EQUIPMENT_DEFECT_CAUGHT", mid, unit_id, "residue detected at functional test; reject")
                rejected = True
        if mid == "quality_01" and unit_id in self.defects:
            inspected = bool(sim.living and unit_id in sim.living.inspection_units)
            if rejected or inspected or rng.random() < .95 - self.risk(mid):
                c.catches += 1
                rejected = True
                if inspected and sim.living:
                    sim.living.captured_units += 1
                    sim._record("LATENT_DEFECT_CONTAINED", mid, unit_id, "wash residue")
                sim._record("EQUIPMENT_DEFECT_CAUGHT", mid, unit_id, "residue isolated at final quality")
            else:
                self.escaped_ids.add(unit_id)
                if sim.living:
                    sim.living.escaped_ids.add(unit_id)
                sim._record("EQUIPMENT_DEFECT_RELEASED", mid, unit_id, "sampling missed residue; suspect finished goods")
            del self.defects[unit_id]
        if rejected:
            self.defects.pop(unit_id, None)
        return rejected

    def active_shortage(self, mid: str) -> bool:
        return bool(self.sim.living and any(
            e.kind == "operator_shortage" and e.zone == mid and e.state == "active"
            for e in self.sim.living.events.values()
        ))

    def effective_cycle_multiplier(self, mid: str) -> float:
        multiplier = self.multiplier(mid) * (1.4 if self.active_shortage(mid) else 1)
        if mid == "quality_01" and self.sim.living and self.sim.living.containment_active:
            multiplier += .6 / self.sim.machines[mid].config.ideal_cycle_minutes
        return multiplier

    def metric(self, mid: str) -> dict[str, Any]:
        if mid not in self.conditions:
            machine = self.sim.machines[mid]
            issue = "spindle breakdown" if machine.state == MachineState.DOWN else "spindle wear warning" if machine.health < 65 else None
            return {"condition_label": "Spindle health", "condition_value": round(self.sim.machines[mid].health, 2),
                    "cycle_time_multiplier": 1.0, "rework": 0, "quality_risk": 0,
                    "active_issue": issue, "service": None, "action_history": [],
                    "maintenance_history": self.maintenance_history(mid)}
        c = self.conditions[mid]
        return {"condition_label": SPECS[mid].label, "condition_value": round(self.pressure(mid), 2),
                "cycle_time_multiplier": round(self.effective_cycle_multiplier(mid), 3), "rework": c.rework,
                "quality_risk": round(self.risk(mid), 4),
                "active_issue": "staffing shortage" if self.active_shortage(mid) else SPECS[mid].fault if self.pressure(mid) >= 45 else None,
                "service": {"action": SPECS[mid].action, "label": SPECS[mid].action_label, "cost": SPECS[mid].cost,
                            "duration": SPECS[mid].duration, "pending": c.pending, "active": c.active,
                            "unavailable_reason": self.unavailable(mid)} if SPECS[mid].action else None,
                "action_history": [dict(row) for row in c.history],
                "maintenance_history": self.maintenance_history(mid)}

    def maintenance_history(self, mid: str) -> list[dict[str, Any]]:
        kinds = {"MACHINE_FAILED", "REPAIR_COMPLETED", "REPAIR_EXPEDITED",
                 "PLANNED_MAINTENANCE_STARTED", "PLANNED_MAINTENANCE_COMPLETED",
                 "EQUIPMENT_SERVICE_REQUESTED", "EQUIPMENT_SERVICE_STARTED",
                 "EQUIPMENT_SERVICE_COMPLETED"}
        return [{"minute": e.time, "kind": e.kind, "detail": e.detail}
                for e in self.sim.event_log if e.machine_id == mid and e.kind in kinds]

    def quality_summary(self) -> dict[str, int]:
        escaped = self.escaped_ids | (self.sim.living.escaped_ids if self.sim.living else set())
        delivered = escaped & self.sim.finished_goods.allocated_order_by_unit.keys()
        return {"source_rejects": sum(c.source_rejects for c in self.conditions.values()),
                "downstream_catches": sum(c.catches for c in self.conditions.values()),
                "rework": sum(c.rework for c in self.conditions.values()),
                "customer_escapes": len(delivered), "suspect_finished_goods": len(escaped - delivered),
                "latent_wip": len(self.defects)}
