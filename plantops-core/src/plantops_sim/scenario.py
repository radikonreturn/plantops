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
            health_loss_per_processed_unit=0.3,
            wear_based_failure_multiplier=2.0,
            preventive_maintenance_duration=20,
            preventive_maintenance_cost=250,
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


def make_seeded_line(base: Scenario) -> Scenario:
    """Expanded bracket line. Classic configuration and RNG consumption stay intact."""
    from dataclasses import replace

    stages = (
        StageConfig("laser_01", "Laser / Cutting", 0.95, 0.10,
                    failure_probability=0.012, repair_min_minutes=5, repair_max_minutes=12,
                    health_loss_per_processed_unit=0.16, wear_based_failure_multiplier=4,
                    preventive_maintenance_duration=12, preventive_maintenance_cost=140),
        replace(base.stages[0], name="CNC Machining", failure_probability=0.018),
        StageConfig("wash_01", "Wash Cell", 0.72, 0.08,
                    failure_probability=0.01, repair_min_minutes=6, repair_max_minutes=14,
                    health_loss_per_processed_unit=0.12, wear_based_failure_multiplier=4,
                    preventive_maintenance_duration=15, preventive_maintenance_cost=120),
        StageConfig("assembly_01", "Assembly Cell", 1.08, 0.12,
                    failure_probability=0.008, repair_min_minutes=4, repair_max_minutes=11,
                    health_loss_per_processed_unit=0.10, wear_based_failure_multiplier=4,
                    preventive_maintenance_duration=10, preventive_maintenance_cost=100),
        StageConfig("test_01", "Test / CMM", 1.05, 0.06,
                    failure_probability=0.009, repair_min_minutes=8, repair_max_minutes=16,
                    health_loss_per_processed_unit=0.10, wear_based_failure_multiplier=4,
                    preventive_maintenance_duration=18, preventive_maintenance_cost=180),
        replace(base.stages[-1], name="Final Quality"),
    )
    return replace(base, stages=stages, buffer_capacities={
        "raw": None, "after_laser_01": 20, "after_cnc_01": 18,
        "after_wash_01": 14, "after_assembly_01": 16, "after_test_01": 12,
        "finished": None,
    })


# Display semantics are keyed by asset identity, never by route position.
MACHINE_METADATA = {
    "laser_01": ("laser", "Lens contamination / assist-gas instability", "Clean lens / purge gas"),
    "cnc_01": ("cnc", "Spindle and tool wear", "Spindle and tool service"),
    "wash_01": ("wash", "Bath concentration / filter differential", "Replace filter / replenish chemical"),
    "assembly_01": ("assembly", "Staffing shortage / torque tool verification", "Assign cross-trained operator"),
    "test_01": ("test", "Calibration drift / false failures", "Recalibrate tester"),
    "quality_01": ("quality", "Inspection load / containment pressure", ""),
}
