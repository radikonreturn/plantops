"""Seeded shift configuration and read-only projections for the operator console.

Seeded profile v2 uses its own named RNG streams. Snapshot generation never draws randomness
or changes the event log. Classic API clients retain their original scenario.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import ceil
from typing import Any

from .engine import ProductionLineSimulation, RandomStreams
from .model import OrderConfig, Scenario
from .scenario import MACHINE_METADATA, make_seeded_line


@dataclass(frozen=True)
class ShiftProfile:
    id: str
    title: str
    briefing: str
    primary_zone: str | None = None


CLASSIC_PROFILE = ShiftProfile(
    "classic-v1", "Standard production shift",
    "Protect delivery commitments on the single component line. Check material "
    "coverage before releasing purchasing decisions and watch CNC health.",
)

@dataclass(frozen=True)
class ProfileDefinition:
    key: str
    title: str
    zone: str
    stock: int
    queue_buffer: str | None
    briefing: str
    cycle_minutes: float | None = None


PROFILE_DEFINITIONS = (
    ProfileDefinition("cnc-wear", "CNC wear risk", "cnc_01", 210, "after_laser_01",
        "The bracket line inherits spindle and tool wear at CNC. Cut blanks are waiting. "
        "Choose a planned spindle service before startup or accept higher breakdown risk to protect dispatch."),
    ProfileDefinition("laser-jam", "Laser optical contamination", "laser_01", 310, None,
        "Receiving has delivered a large sheet-blank lot, but the cutting nozzle is in poor condition. "
        "Contamination slows cuts and increases edge scrap. Clean the lens and purge assist gas before losses grow."),
    ProfileDefinition("wash-filter", "Wash filter restriction", "wash_01", 210, "after_cnc_01",
        "Machined brackets are queued before a restricted wash cell. Bath residue can travel downstream undetected. "
        "Filter and chemical service removes future exposure; inspect existing suspect WIP. The base wash cycle remains constrained.", 1.55),
    ProfileDefinition("assembly-fixture", "Assembly tooling and staffing pressure", "assembly_01", 200, "after_wash_01",
        "The previous shift left clean brackets at assembly. Torque tooling and staffing pressure slow work and add rechecks. A single "
        "fixture limits base capacity. Cross-trained support restores working condition and resolves active staffing shortages.", 1.65),
    ProfileDefinition("test-calibration", "Test calibration pressure", "test_01", 220, "after_assembly_01",
        "Assembled brackets await functional test and CMM checks. Drift causes false failures, retests and missed residue "
        "defects. Recalibration restores detection and removes drift-related cycle losses; base test capacity remains constrained.", 1.50),
    ProfileDefinition("quality-containment", "Quality containment", "quality_01", 240, "after_test_01",
        "Final inspection is receiving a suspect bracket lot with elevated rejection probability. "
        "Inspection load slows release. Allow replacement material and review delivery commitments. "
        "Intensified containment catches latent defects at added time and cost; it does not change source lot risk."),
    ProfileDefinition("material-shortage", "Material shortage", "raw", 45, None,
        "Receiving has few steel blanks and the supplier has a long, less reliable lead time. "
        "Place a purchase order early to prevent starvation at cutting and across the bracket line."),
    ProfileDefinition("rush-dispatch", "Competing rush orders", "dispatch", 155, "after_assembly_01",
        "Two bracket orders share the first dispatch window. Carry-in WIP is near test and final release. "
        "Set relative order priority and fund replacement stock: dispatching one customer first can delay the other."),
)


def make_seeded_shift(base: Scenario, seed: int) -> tuple[Scenario, ShiftProfile]:
    streams = RandomStreams(seed)
    definition = streams.get("scenario-profile:v2").choice(PROFILE_DEFINITIONS)
    rng = streams.get("scenario-conditions:v2")
    line = make_seeded_line(base)
    stages = []
    for stage in line.stages:
        stage = replace(stage, initial_health=92 + rng.randint(0, 8))
        if stage.id == definition.zone and stage.id != "quality_01":
            stage = replace(stage, initial_health=32 + rng.randint(0, 12),
                            wear_based_failure_multiplier=5)
        if stage.id == definition.zone and definition.cycle_minutes:
            stage = replace(stage, ideal_cycle_minutes=definition.cycle_minutes)
        if stage.id == "quality_01" and definition.zone == "quality_01":
            stage = replace(stage, scrap_probability=0.14)
        if stage.id == "cnc_01" and definition.zone != "cnc_01":
            cnc_rng = streams.get("machine:cnc:shift")
            stage = replace(stage, failure_probability=cnc_rng.uniform(.0002, .003))
        stages.append(stage)
    rush = definition.zone == "dispatch"
    shortage = definition.zone == "raw"
    first_due = (105 if rush else 150) + rng.randint(0, 15)
    orders = tuple(OrderConfig(
        id=f"ORDER-{i + 1:03d}", quantity=(65, 80, 90)[i] + rng.randint(0, 15),
        release_minute=0, due_minute=first_due if i == 0 or (rush and i == 1)
        else (310 if i == 1 else 455) + rng.randint(0, 10), priority=rng.randint(10, 40),
    ) for i in range(3))
    supplier = replace(base.suppliers[0],
        min_lead_minutes=95 if shortage else 60 + rng.randint(0, 10),
        max_lead_minutes=125 if shortage else 90 + rng.randint(0, 10),
        late_probability=0.35 if shortage else 0.2,
    )
    wip = tuple((name, (capacity - rng.randint(0, 2)
                       if name == definition.queue_buffer else rng.randint(0, 3)))
                for name, capacity in line.buffer_capacities.items()
                if capacity is not None)
    return replace(line, raw_material_units=definition.stock + rng.randint(0, 24),
                   stages=tuple(stages), orders=orders, suppliers=(supplier,), initial_wip=wip), ShiftProfile(
        f"{definition.key}-v2", definition.title, definition.briefing, definition.zone)


def profile_snapshot(
    simulation: ProductionLineSimulation, profile: ShiftProfile, summary: dict[str, Any],
) -> dict[str, Any]:
    """Scene geometry is fixed; scene content and concerns are projections of stock/state."""
    scenario = simulation.scenario
    order_summary = summary["order_summary"]
    supply = summary["supply_summary"]
    alerts: list[dict[str, str]] = []

    def alert(key: str, zone: str, severity: str, message: str, workspace: str) -> None:
        alerts.append(dict(id=key, zone=zone, severity=severity, message=message,
                           workspace=workspace))

    machines = []
    for stage in scenario.stages:
        machine = simulation.machines[stage.id]
        role, fault_mode, maintenance_label = MACHINE_METADATA[stage.id]
        reason = None
        if machine.state == "DOWN":
            reason = f"{fault_mode}: stopped for repair."
            alert(f"down-{stage.id}", stage.id, "critical",
                  f"{stage.name} is DOWN ({fault_mode.lower()}). Review emergency repair.", "Maintenance")
        elif machine.health < 65 and stage.failure_probability > 0:
            reason = f"{fault_mode}: health {machine.health:.1f}/100."
            alert(f"wear-{stage.id}", stage.id, "attention",
                  f"{stage.name}: {fault_mode.lower()}; health {machine.health:.1f}/100, "
                  f"{'failure' if role == 'cnc' or not simulation.equipment else 'condition upset'} risk {simulation.effective_failure_probability(stage.id):.1%} per unit.", "Maintenance")
        elif machine.state == "PLANNED_MAINTENANCE":
            reason = f"{maintenance_label} in progress."
        elif machine.state == "BLOCKED":
            reason = f"Output buffer {machine.output_buffer} is full."
        elif machine.state == "STARVED":
            reason = f"Waiting for material in {machine.input_buffer}."
        if stage.scrap_probability > 0.05:
            reason = f"Configured lot rejection {stage.scrap_probability:.0%}; {machine.scrap_units} observed scrap."
        equipment = summary["machine_metrics"][stage.id] if simulation.equipment else {}
        if equipment.get("active_issue"):
            reason = equipment["active_issue"]
            alert(f"condition-{stage.id}", stage.id, "attention", f"{stage.id.replace('_', '-').upper()}: {reason}",
                  "Quality" if role == "quality" else "Maintenance")
        if equipment.get("service") and equipment["service"]["pending"]:
            reason = "Service queued; current unit will finish first."
        machines.append({
            "id": stage.id, "name": stage.name if profile.primary_zone else stage.id.replace("_", "-").upper(),
            "stage_role": role, "fault_mode": fault_mode,
            "ideal_cycle_minutes": stage.ideal_cycle_minutes,
            "failure_risk": simulation.effective_failure_probability(stage.id),
            "maintenance_available": stage.preventive_maintenance_duration > 0,
            "maintenance_label": maintenance_label,
            "maintenance_unavailable_reason": None if stage.preventive_maintenance_duration > 0
            else ("Final inspection rejects the configured lot; equipment service cannot change lot quality."
                  if role == "quality" else "No preventive maintenance is configured for this stage."),
            "maintenance_duration": stage.preventive_maintenance_duration,
            "maintenance_cost": stage.preventive_maintenance_cost,
            "scrap_probability": stage.scrap_probability,
            "input_buffer": machine.input_buffer, "output_buffer": machine.output_buffer,
            "status": machine.state, "attention_reason": reason,
        })

    in_process = sum(m.busy_unit is not None for m in simulation.machines.values())
    coverage = (supply["raw_material_on_hand"] + supply["inbound_units"]
                + summary["wip"] + in_process + summary["finished_goods_available"])
    remaining_demand = sum(o["remaining_quantity"] for o in order_summary["orders"])
    if remaining_demand > coverage:
        alert("material-coverage", "raw", "attention",
              f"{remaining_demand - coverage} units of demand lack material coverage before scrap allowance.",
              "Inventory")
    if scenario.stages[-1].scrap_probability > 0.05:
        alert("quality-risk", scenario.stages[-1].id, "attention",
              f"Lot reject risk is {scenario.stages[-1].scrap_probability:.0%}; "
              f"{summary['scrap']} units have actually been scrapped.", "Quality")

    zones = []
    for buffer_id, buffer in simulation.buffers.items():
        units = summary["finished_goods_available"] if buffer_id == "finished" else buffer.size
        capacity = buffer.capacity
        congested = capacity is not None and units >= capacity * 0.75
        if congested:
            alert(f"queue-{buffer_id}", buffer_id, "attention",
                  f"{buffer_id.replace('_', ' ')}: {units}/{capacity} places occupied.", "Production Plan")
        # A pallet represents at most 20 raw/finished units or 2 WIP units.
        pallet_capacity = 20 if buffer_id in {"raw", "finished"} else 2
        zones.append({"id": buffer_id, "units": units, "capacity": capacity,
                      "pallets": ceil(units / pallet_capacity),
                      "units_per_pallet": pallet_capacity, "congested": congested})

    # Optimistic dispatch estimate, deliberately labelled: no losses or inbound waits.
    bottleneck_cycle = max(s.ideal_cycle_minutes for s in scenario.stages)
    cumulative = 0
    risks = {}
    forecasts = {}
    for order in sorted(order_summary["orders"], key=lambda o: (o["due_minute"], -o["priority"], o["id"])):
        cumulative += order["remaining_quantity"]
        if order["remaining_quantity"] == 0:
            risk = "Delivered late" if order["status"] == "COMPLETED_LATE" else "Delivered"
        elif order["status"] == "PENDING":
            risk = "Scheduled"
        elif order["status"] == "LATE":
            risk = "Late"
        elif simulation.clock + cumulative * bottleneck_cycle > order["due_minute"]:
            risk = "At risk"
        else:
            risk = "Open"
        risks[order["id"]] = risk
        forecasts[order["id"]] = (round(simulation.clock + cumulative * bottleneck_cycle, 2)
                                     if order["remaining_quantity"] else None)
    for order_id, risk in risks.items():
        if risk in {"Late", "At risk"}:
            alert(f"order-{order_id}", "dispatch", "critical" if risk == "Late" else "attention",
                  f"{order_id}: {risk.lower()} against its dispatch deadline.", "Orders")
    if supply["purchase_orders_open"]:
        alert("inbound", "receiving", "info",
              f"{supply['inbound_units']} units inbound on {supply['purchase_orders_open']} open POs.", "Inventory")
    for event in summary.get("shift_events", []):
        if event["state"] == "active":
            alert(event["id"], event["zone"], event["severity"],
                  f"{event['title']}: {event['detail']}", event["workspace"])
    # Put the handover concern first when it is still true, after severity ordering.
    alerts.sort(key=lambda a: ({"critical": 0, "attention": 1, "info": 2}[a["severity"]],
                               a["zone"] != profile.primary_zone, a["id"]))
    routes = [
        {"id": stage.id, "from": simulation.machines[stage.id].input_buffer,
         "to": simulation.machines[stage.id].output_buffer,
         "active": simulation.machines[stage.id].state == "RUNNING",
         "blocked": not simulation.buffers[simulation.machines[stage.id].output_buffer].can_take(),
         "waiting_units": simulation.buffers[simulation.machines[stage.id].input_buffer].size,
         "status": simulation.machines[stage.id].state}
        for stage in scenario.stages
    ]
    return {
        **asdict(profile), "active_alerts": alerts, "machines": machines,
        "suppliers": [asdict(s) for s in scenario.suppliers],
        "initial_conditions": {
            "raw_units": scenario.raw_material_units, "wip": dict(scenario.initial_wip),
            "machine_health": {s.id: s.initial_health for s in scenario.stages},
        },
        "scene": {"zones": zones, "routes": routes,
                  "highlighted_zone": alerts[0]["zone"] if alerts else None,
                  "machine_concerns": {m["id"]: m["attention_reason"] for m in machines
                                       if m["attention_reason"]},
                  "receiving": {"inbound_units": supply["inbound_units"],
                                "open_purchase_orders": supply["purchase_orders_open"],
                                "uncovered_demand": max(0, remaining_demand - coverage)},
                  "dispatch": {"allocated_units": summary["finished_goods_allocated"],
                               "at_risk_orders": sum(r in {"Late", "At risk"} for r in risks.values())},
                  "order_risks": risks, "order_forecasts": forecasts},
        "capacity": {"bottleneck_cycle_minutes": bottleneck_cycle,
                     "bottleneck_machines": [s.id for s in scenario.stages
                                             if s.ideal_cycle_minutes == bottleneck_cycle],
                     "ideal_shift_units": int(summary["shift_minutes"] / bottleneck_cycle),
                     "estimate_note": "Ideal capacity only; excludes failures, scrap, starvation and carried-in WIP."},
        "decision_cards": decision_cards(simulation, profile, summary, machines, risks),
        "shift_review": shift_review(simulation, profile, summary, alerts),
    }


def action_log(simulation: ProductionLineSimulation) -> list[dict[str, Any]]:
    kinds = {"REPAIR_EXPEDITED", "PLANNED_MAINTENANCE_STARTED",
             "ORDER_PRIORITY_CHANGED", "PURCHASE_ORDER_PLACED",
             "PURCHASE_ORDER_EXPEDITED", "OVERTIME_AUTHORIZED", "QUALITY_CONTAINMENT_ACTIVATED", "EQUIPMENT_SERVICE_REQUESTED"}
    return [
        {"id": index, "minute": event.time, "kind": event.kind,
         "machine_id": event.machine_id, "detail": event.detail}
        for index, event in enumerate(simulation.event_log) if event.kind in kinds
    ]


def decision_cards(
    simulation: ProductionLineSimulation,
    profile: ShiftProfile,
    summary: dict[str, Any],
    machines: list[dict[str, Any]],
    risks: dict[str, str],
) -> list[dict[str, Any]]:
    """Three compact, state-backed decision prompts for the current shift.

    These are not scripted quests: their status reflects actions and operational state
    in this simulation session. They deliberately describe the decision, not a "right"
    answer, because trade-offs are the point of the game.
    """
    action_kinds = {event.kind for event in simulation.event_log}
    cards: list[dict[str, Any]] = []
    machine = next((item for item in machines if item["id"] == profile.primary_zone), None)

    if machine and machine["maintenance_available"]:
        completed = any(
            event.kind in {"PLANNED_MAINTENANCE_STARTED", "REPAIR_EXPEDITED", "EQUIPMENT_SERVICE_REQUESTED"} and event.machine_id == machine["id"]
            for event in simulation.event_log
        )
        service = summary["machine_metrics"][machine["id"]].get("service")
        service_detail = (
            f"{service['label']}: {service['duration']:g} minutes stopped / "
            f"{service['cost']:g} cost / restores underlying condition after the current unit."
            if service else f"Service: {machine['maintenance_duration']:g} minutes stopped / "
            f"{machine['maintenance_cost']:g} cost / restores health to 100."
        )
        cards.append({
            "id": "protect-asset",
            "title": f"Decide on {machine['name']}",
            "detail": (
                f"{machine['fault_mode']}. {machine['attention_reason'] or 'Review health, queue and delivery exposure before acting.'} "
                f"{service_detail}"
            ),
            "workspace": "Maintenance",
            "status": "decision logged" if completed else "open decision",
        })
    elif profile.primary_zone == "raw":
        supplied = "PURCHASE_ORDER_PLACED" in action_kinds
        uncovered = summary["supply_summary"]["inbound_units"] + summary["supply_summary"]["raw_material_on_hand"]
        cards.append({
            "id": "secure-material",
            "title": "Secure material coverage",
            "detail": (
                f"The line has {uncovered} units of available or inbound material. "
                "Purchasing commits quantity × unit cost. Expedite an open PO for 120 cost to halve its remaining transit time; later disruption can still delay it."
            ),
            "workspace": "Inventory",
            "status": "decision logged" if supplied else "open decision",
        })
    elif profile.primary_zone == "quality_01":
        cards.append({
            "id": "contain-quality",
            "title": "Plan for quality containment",
            "detail": (
                "Source rejection risk remains unchanged. Containment isolates latent defects in newly inspected units; "
                "each inspection adds 0.6 minutes and 2 cost, exposing delivery."
            ),
            "workspace": "Quality",
            "status": "decision logged; source risk remains" if "QUALITY_CONTAINMENT_ACTIVATED" in action_kinds else "still open",
        })
    elif profile.primary_zone == "dispatch":
        reprioritized = "ORDER_PRIORITY_CHANGED" in action_kinds
        cards.append({
            "id": "protect-dispatch",
            "title": "Choose a dispatch priority",
            "detail": (
                "Orders share a delivery window. Priority changes the allocation order when finished goods are scarce; "
                "it can protect one customer while exposing another."
            ),
            "workspace": "Orders",
            "status": "decision logged" if reprioritized else "open decision",
        })

    upcoming = next(
        (order for order in sorted(summary["order_summary"]["orders"], key=lambda item: (item["due_minute"], item["id"]))
         if order["remaining_quantity"] > 0),
        None,
    )
    if upcoming:
        cards.append({
            "id": "protect-customer",
            "title": f"Protect {upcoming['id']}",
            "detail": (
                f"{upcoming['remaining_quantity']} units remain due at minute {upcoming['due_minute']}. "
                f"Current delivery outlook: {risks[upcoming['id']].lower()}."
            ),
            "workspace": "Orders",
            "status": risks[upcoming["id"]].lower(),
        })

    cards.append({
        "id": "shift-extension",
        "title": "Consider one overtime extension",
        "detail": (
            "60 extra production minutes / 600 labor cost. Failure exposure increases 20% only during overtime. "
            "Authorize before shift close; due dates remain unchanged."
        ),
        "workspace": "Production Plan",
        "status": "decision logged" if "OVERTIME_AUTHORIZED" in action_kinds else "still open",
    })
    for card in cards:
        if card["id"] == "protect-customer":
            card["detail"] += " Priority changes only same-deadline allocation; protecting one order may expose another."
            card["decision_logged"] = any(e.kind == "ORDER_PRIORITY_CHANGED" and f"order_id={upcoming['id']};" in e.detail for e in simulation.event_log)
        else:
            card["decision_logged"] = "decision logged" in card["status"]
        if simulation.clock >= summary["shift_minutes"]:
            card["status"] = "outcome observed" + ("; decision logged" if card["decision_logged"] else "; no decision logged")
    return cards[:3]


def shift_review(
    simulation: ProductionLineSimulation,
    profile: ShiftProfile,
    summary: dict[str, Any],
    alerts: list[dict[str, str]],
) -> dict[str, Any]:
    """Evidence-based management review for interim and completed shifts."""
    order_summary = summary["order_summary"]
    metrics = summary["machine_metrics"]
    final = simulation.clock >= summary["shift_minutes"]
    failures = sum(metric["failures"] for metric in metrics.values())
    downtime = sum(metric["unplanned_downtime_minutes"] for metric in metrics.values())
    committed_procurement = summary["supply_summary"]["procurement_committed_cost"]
    quality = summary["quality"]
    due = order_summary["orders_due"]
    otif = order_summary["otif"]
    delivery_status = (
        "good" if (due == 0 or (otif is not None and otif >= 0.95))
        else "attention" if otif is not None and otif >= 0.70 else "critical"
    )
    if not final and any(alert["zone"] == "dispatch" for alert in alerts):
        delivery_status = "attention"
    quality_status = "good" if quality >= 0.97 else "attention" if quality >= 0.90 else "critical"
    if not simulation.machines[simulation.scenario.stages[-1].id].processed_units:
        quality_status = "attention"
    escapes = summary.get("quality_containment", {}).get("customer_escapes", 0)
    if escapes:
        quality_status = "critical"
    resilience_status = "good" if failures == 0 else "attention" if failures <= 2 else "critical"
    cost_status = "good" if committed_procurement == 0 else "attention"
    delivery_value = (
        f"OTIF {otif:.0%} across {due} due orders" if due and otif is not None
        else ("No customer order due yet" if not final else "No customer order became due")
    )
    actions = action_log(simulation)
    if final:
        headline = "Shift review: delivery protected" if delivery_status == "good" else "Shift review: customer exposure remains"
        conclusion = (
            "The review records observed outcomes; it does not infer that one action alone caused them. "
            "Use the action log together with the machine and order history in the next shift handover."
        )
    else:
        headline = "Interim management review"
        conclusion = "Provisional live report. Delivery and quality outcomes are final only at shift close."
    if final:
        conclusion = (f"Observed outcome: {order_summary['units_delivered']} units delivered, "
                      f"{order_summary['backlog_units']} backlog, {summary['scrap']} scrap and "
                      f"{downtime:.1f} summed machine downtime minutes. " + conclusion)
    return {
        "state": "final" if final else "interim",
        "headline": headline,
        "conclusion": conclusion,
        "actions_recorded": len(actions),
        "event_history": summary.get("shift_events", []),
        "quality_containment": summary.get("quality_containment"),
        "scorecard": [
            {"id": "delivery", "label": "Customer delivery", "status": delivery_status, "value": delivery_value},
            {"id": "quality", "label": "Quality yield", "status": quality_status,
             "value": (f"{quality:.1%} inspection yield · {summary['scrap']} scrap · {escapes} customer escapes"
                       if simulation.machines[simulation.scenario.stages[-1].id].processed_units else "No inspections completed yet")},
            {"id": "resilience", "label": "Equipment resilience", "status": resilience_status,
             "value": f"{failures} failure(s) · {downtime:.1f} unplanned min"},
            {"id": "cost", "label": "Procurement commitment", "status": cost_status,
             "value": f"{committed_procurement:.2f} committed material cost"},
        ],
    }
