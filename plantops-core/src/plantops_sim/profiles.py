"""Seeded shift configuration and read-only projections for the operator console.

Profile v1 uses its own named RNG stream. Snapshot generation never draws randomness
or changes the event log. Classic API clients retain their original scenario.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import ceil
from typing import Any

from .engine import ProductionLineSimulation, RandomStreams
from .model import OrderConfig, Scenario


@dataclass(frozen=True)
class ShiftProfile:
    id: str
    title: str
    briefing: str


CLASSIC_PROFILE = ShiftProfile(
    "classic-v1", "Standard production shift",
    "Protect delivery commitments on the single component line. Check material "
    "coverage before releasing purchasing decisions and watch CNC health.",
)

PROFILE_DEFINITIONS = (
    ("delivery-recovery", "Delivery recovery", 180, 86, 3,
     "Recover the first dispatch commitment. Carry-in WIP is occupying the line; "
     "check downstream queues before committing to maintenance."),
    ("material-shortage", "Material shortage", 55, 94, 0,
     "Receiving has limited steel blanks and the supplier has a long lead time. "
     "Place a purchase order early enough to avoid a starved CNC."),
    ("quality-containment", "Quality containment", 240, 92, 2,
     "Quality has flagged an elevated reject risk in this production lot. "
     "Monitor actual scrap and allow material coverage for replacement units. "
     "Inspection remains automatic; there is no manual release override."),
    ("maintenance-risk", "Maintenance risk", 210, 38, 1,
     "The CNC arrives from the previous shift with significant wear. Decide "
     "whether a planned stop now is worth the reduction in failure risk."),
    ("rush-dispatch", "Competing rush orders", 150, 74, 2,
     "Two customer commitments share the first dispatch window. Set their "
     "relative priority carefully: rushing one may delay the other. "
     "All orders still use the same product family."),
)


def make_seeded_shift(base: Scenario, seed: int) -> tuple[Scenario, ShiftProfile]:
    rng = RandomStreams(seed).get("scenario-profile:v1")
    index = rng.randrange(len(PROFILE_DEFINITIONS))
    key, title, stock, health, queue, briefing = PROFILE_DEFINITIONS[index]
    raw_units = stock + rng.randint(0, 24)
    stages = list(base.stages)
    stages[0] = replace(stages[0], initial_health=health + rng.randint(0, 5))
    if index == 2:
        stages[-1] = replace(stages[-1], scrap_probability=0.11)
    first_due = (100, 150, 160, 170, 135)[index] + rng.randint(0, 10)
    orders = tuple(
        OrderConfig(
            id=f"ORDER-{i + 1:03d}",
            quantity=(65, 80, 90)[i] + rng.randint(0, 15),
            release_minute=0,
            due_minute=first_due if i == 0 or (index == 4 and i == 1)
            else (310 if i == 1 else 455) + rng.randint(0, 10),
            priority=rng.randint(10, 40),
        )
        for i in range(3)
    )
    supplier = replace(
        base.suppliers[0],
        min_lead_minutes=95 if index == 1 else 60,
        max_lead_minutes=125 if index == 1 else 90,
        late_probability=0.35 if index == 1 else 0.2,
    )
    wip = tuple(
        (name, min(base.buffer_capacities[name] or 0, queue * 4 + rng.randint(0, 2)))
        for name in ("after_cnc_01", "after_wash_01", "after_assembly_01")
    ) if queue else ()
    return replace(
        base, raw_material_units=raw_units, stages=tuple(stages), orders=orders,
        suppliers=(supplier,), initial_wip=wip,
    ), ShiftProfile(f"{key}-v1", title, briefing)


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
        if machine.state == "DOWN":
            alert(f"down-{stage.id}", stage.id, "critical",
                  f"{stage.id.replace('_', '-').upper()} is DOWN. Review emergency repair.", "Maintenance")
        elif machine.health < 65 and stage.failure_probability > 0:
            alert(f"wear-{stage.id}", stage.id, "attention",
                  f"CNC health is {machine.health:.1f}/100; wear increases breakdown risk.", "Maintenance")
        machines.append({
            "id": stage.id, "name": stage.id.replace("_", "-").upper(),
            "ideal_cycle_minutes": stage.ideal_cycle_minutes,
            "failure_risk": simulation.effective_failure_probability(stage.id),
            "maintenance_duration": stage.preventive_maintenance_duration,
            "maintenance_cost": stage.preventive_maintenance_cost,
            "scrap_probability": stage.scrap_probability,
            "input_buffer": machine.input_buffer, "output_buffer": machine.output_buffer,
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
    for order_id, risk in risks.items():
        if risk in {"Late", "At risk"}:
            alert(f"order-{order_id}", "dispatch", "critical" if risk == "Late" else "attention",
                  f"{order_id}: {risk.lower()} against its dispatch deadline.", "Orders")
    if supply["purchase_orders_open"]:
        alert("inbound", "receiving", "info",
              f"{supply['inbound_units']} units inbound on {supply['purchase_orders_open']} open POs.", "Inventory")
    alerts.sort(key=lambda a: ({"critical": 0, "attention": 1, "info": 2}[a["severity"]], a["id"]))
    routes = [
        {"id": stage.id, "from": simulation.machines[stage.id].input_buffer,
         "to": simulation.machines[stage.id].output_buffer,
         "active": simulation.machines[stage.id].state == "RUNNING"}
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
                  "order_risks": risks},
        "capacity": {"bottleneck_cycle_minutes": bottleneck_cycle,
                     "ideal_shift_units": int(scenario.shift_minutes / bottleneck_cycle),
                     "estimate_note": "Ideal capacity only; excludes failures, scrap, starvation and carried-in WIP."},
    }


def action_log(simulation: ProductionLineSimulation) -> list[dict[str, Any]]:
    kinds = {"REPAIR_EXPEDITED", "PLANNED_MAINTENANCE_STARTED",
             "ORDER_PRIORITY_CHANGED", "PURCHASE_ORDER_PLACED"}
    return [
        {"id": index, "minute": event.time, "kind": event.kind,
         "machine_id": event.machine_id, "detail": event.detail}
        for index, event in enumerate(simulation.event_log) if event.kind in kinds
    ]
