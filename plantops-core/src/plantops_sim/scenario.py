from __future__ import annotations

from .model import (
    OrderConfig,
    Scenario,
    StageConfig,
    SupplierConfig,
    UrgentOrderRule,
)


def make_mvp_scenario(
    *,
    raw_material_units: int = 200,
    shift_minutes: float = 480,
    cnc_failure_probability: float = 0.055,
) -> Scenario:
    """Single automotive component line used by the first playable PlantOps scenario."""
    stages = (
        StageConfig(
            id="cnc_01", name="CNC-01", ideal_cycle_minutes=1.35, cycle_jitter=0.15,
            failure_probability=cnc_failure_probability, repair_min_minutes=7, repair_max_minutes=18,
        ),
        StageConfig(id="wash_01", name="Yıkama-01", ideal_cycle_minutes=0.72, cycle_jitter=0.08),
        StageConfig(id="assembly_01", name="Montaj-01", ideal_cycle_minutes=1.08, cycle_jitter=0.12),
        StageConfig(
            id="quality_01", name="Kalite-01", ideal_cycle_minutes=0.46, cycle_jitter=0.05,
            scrap_probability=0.032,
        ),
    )
    orders = (
        OrderConfig(
            id="ORDER-001",
            quantity=70,
            release_minute=0,
            due_minute=150,
            priority=2,
        ),
        OrderConfig(
            id="ORDER-002",
            quantity=90,
            release_minute=0,
            due_minute=320,
            priority=1,
        ),
        OrderConfig(
            id="ORDER-003",
            quantity=100,
            release_minute=0,
            due_minute=470,
            priority=1,
        ),
    )
    urgent_order_rule = UrgentOrderRule(
        id="ORDER-URGENT",
        min_arrival_minute=120,
        max_arrival_minute=210,
        min_quantity=35,
        max_quantity=50,
        lead_time_minutes=70,
        priority=10,
    )
    suppliers = (
        SupplierConfig(
            id="STEEL-01",
            name="Anatolia Steel Blanks",
            min_lead_minutes=60,
            max_lead_minutes=90,
            late_probability=0.2,
            max_delay_minutes=45,
            unit_cost=18.5,
        ),
    )
    return Scenario(
        raw_material_units=raw_material_units,
        shift_minutes=shift_minutes,
        stages=stages,
        buffer_capacities={
            "raw": None,
            "after_cnc_01": 18,
            "after_wash_01": 14,
            "after_assembly_01": 12,
            "finished": None,
        },
        orders=orders,
        urgent_order_rule=urgent_order_rule,
        suppliers=suppliers,
    )
