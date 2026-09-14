from __future__ import annotations

from .model import Scenario, StageConfig


def make_mvp_scenario(
    *,
    raw_material_units: int = 500,
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
    return Scenario(
        raw_material_units=raw_material_units,
        shift_minutes=shift_minutes,
        stages=stages,
        buffer_capacities={
            "raw": raw_material_units,
            "after_cnc_01": 18,
            "after_wash_01": 14,
            "after_assembly_01": 12,
            "finished": None,
        },
    )
