"""A quiet first shift, configured on the production engine rather than a demo."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from .model import OrderConfig, Scenario
from .profiles import ShiftProfile
from .scenario import make_mvp_scenario, make_seeded_line

if TYPE_CHECKING:
    from .engine import ProductionLineSimulation

TUTORIAL_SEED = 0
TUTORIAL_PROFILE = ShiftProfile(
    "tutorial-v1", "First shift: cutting condition",
    "07:55 — Your first shift at Artemis Manufacturing. The previous supervisor "
    "reports slower LASER-01 output and inconsistent cut edges late yesterday. "
    "A priority customer needs 30 brackets by minute 50 of this practice shift. "
    "Read the handover, inspect cutting condition, and weigh service time and cost "
    "against production and quality exposure.", "laser_01",
)


def make_tutorial_scenario() -> Scenario:
    line = make_seeded_line(make_mvp_scenario())
    return replace(
        line, raw_material_units=70, shift_minutes=60, initial_wip=(),
        urgent_order_rule=None,
        orders=(OrderConfig("ORDER-FIRST", 30, 0, 50, 10),),
        stages=tuple(replace(
            stage, initial_health=100, health_loss_per_processed_unit=0,
            failure_probability=1e-12 if stage.id == "laser_01" else 0,
            scrap_probability=0,
        ) for stage in line.stages),
    )


def configure_tutorial(simulation: ProductionLineSimulation) -> None:
    """Initial conditions only; subsequent outcomes use ordinary V4 mechanics."""
    assert simulation.equipment is not None
    for mid, condition in simulation.equipment.conditions.items():
        condition.burden = 65 if mid == "laser_01" else 0
        condition.wear = .05 if mid == "laser_01" else 0
