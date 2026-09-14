from __future__ import annotations

import unittest
from unittest.mock import patch

from plantops_sim import ProductionLineSimulation
from plantops_sim.engine import (
    MachineCannotStartPreventiveMaintenanceError,
    PreventiveMaintenanceNotConfiguredError,
)
from plantops_sim.model import Scenario, StageConfig
from plantops_sim.sessions import SessionManager


def make_maintenance_scenario(
    *,
    raw_material_units: int,
    failure_probability: float = 0,
    health_loss_per_unit: float = 5,
    wear_multiplier: float = 2,
    maintenance_duration: float = 2,
    maintenance_cost: float = 250,
) -> Scenario:
    stages = (
        StageConfig(
            id="cnc_01",
            name="CNC-01",
            ideal_cycle_minutes=1,
            cycle_jitter=0,
            failure_probability=failure_probability,
            repair_min_minutes=5,
            repair_max_minutes=5,
            health_loss_per_processed_unit=health_loss_per_unit,
            wear_based_failure_multiplier=wear_multiplier,
            preventive_maintenance_duration=maintenance_duration,
            preventive_maintenance_cost=maintenance_cost,
        ),
        StageConfig("wash_01", "Wash-01", 1, 0),
        StageConfig("assembly_01", "Assembly-01", 1, 0),
        StageConfig("quality_01", "Quality-01", 1, 0),
    )
    return Scenario(
        raw_material_units=raw_material_units,
        shift_minutes=30,
        stages=stages,
        buffer_capacities={
            "raw": None,
            "after_cnc_01": 10,
            "after_wash_01": 10,
            "after_assembly_01": 10,
            "finished": None,
        },
    )


class PreventiveMaintenanceTests(unittest.TestCase):
    def test_unconfigured_machine_rejects_maintenance_without_mutation(self):
        simulation = ProductionLineSimulation(
            make_maintenance_scenario(raw_material_units=1),
            seed=7,
        )
        summary_before = simulation.summary()
        digest_before = simulation.digest()
        events_before = list(simulation.event_log)

        with self.assertRaises(PreventiveMaintenanceNotConfiguredError):
            simulation.start_preventive_maintenance("WASH-01")

        self.assertEqual(simulation.summary(), summary_before)
        self.assertEqual(simulation.digest(), digest_before)
        self.assertEqual(simulation.event_log, events_before)

    def test_health_decreases_deterministically_after_production(self):
        scenario = make_maintenance_scenario(raw_material_units=3)
        first = ProductionLineSimulation(scenario, seed=7)
        second = ProductionLineSimulation(scenario, seed=7)

        first_summary = first.advance_to(3)
        second_summary = second.advance_to(3)

        self.assertEqual(first.machines["cnc_01"].processed_units, 3)
        self.assertEqual(first_summary["machine_metrics"]["cnc_01"]["health"], 85.0)
        self.assertEqual(first_summary, second_summary)
        self.assertEqual(first.digest(), second.digest())

    def test_lower_health_increases_effective_failure_probability(self):
        simulation = ProductionLineSimulation(
            make_maintenance_scenario(
                raw_material_units=0,
                failure_probability=0.1,
            ),
            seed=7,
        )

        full_health_risk = simulation.effective_failure_probability("CNC-01")
        simulation.machines["cnc_01"].health = 50
        worn_risk = simulation.effective_failure_probability("CNC-01")

        self.assertAlmostEqual(full_health_risk, 0.1)
        self.assertAlmostEqual(worn_risk, 0.2)
        self.assertGreater(worn_risk, full_health_risk)

    def test_maintenance_rejects_running_down_and_active_maintenance(self):
        running = ProductionLineSimulation(
            make_maintenance_scenario(raw_material_units=1),
            seed=7,
        )
        running.advance_to(0)
        with self.assertRaises(MachineCannotStartPreventiveMaintenanceError):
            running.start_preventive_maintenance("CNC-01")

        down = ProductionLineSimulation(
            make_maintenance_scenario(
                raw_material_units=1,
                failure_probability=1,
            ),
            seed=7,
        )
        down.advance_to(1)
        with self.assertRaises(MachineCannotStartPreventiveMaintenanceError):
            down.start_preventive_maintenance("CNC-01")

        maintained = ProductionLineSimulation(
            make_maintenance_scenario(raw_material_units=0),
            seed=7,
        )
        maintained.start_preventive_maintenance("CNC-01")
        summary_before = maintained.summary()
        digest_before = maintained.digest()
        with self.assertRaises(MachineCannotStartPreventiveMaintenanceError):
            maintained.start_preventive_maintenance("CNC-01")
        self.assertEqual(maintained.summary(), summary_before)
        self.assertEqual(maintained.digest(), digest_before)

    def test_maintenance_blocks_production_while_active(self):
        simulation = ProductionLineSimulation(
            make_maintenance_scenario(raw_material_units=2),
            seed=7,
        )

        simulation.start_preventive_maintenance("CNC-01")
        summary = simulation.advance_to(1.5)

        cnc = summary["machine_metrics"]["cnc_01"]
        self.assertEqual(cnc["state"], "PLANNED_MAINTENANCE")
        self.assertEqual(cnc["processed"], 0)
        self.assertEqual(cnc["planned_maintenance_minutes"], 1.5)
        self.assertEqual(summary["raw_material_remaining"], 2)

    def test_completion_resets_health_and_resumes_production_once(self):
        simulation = ProductionLineSimulation(
            make_maintenance_scenario(raw_material_units=2),
            seed=7,
        )
        simulation.machines["cnc_01"].health = 40
        simulation.start_preventive_maintenance("CNC-01")

        completed = simulation.advance_to(2)

        cnc = completed["machine_metrics"]["cnc_01"]
        self.assertEqual(cnc["state"], "RUNNING")
        self.assertEqual(cnc["health"], 100.0)
        self.assertEqual(cnc["maintenance_count"], 1)
        self.assertEqual(cnc["planned_maintenance_minutes"], 2)
        self.assertEqual(
            completed["event_counts"]["PLANNED_MAINTENANCE_COMPLETED"],
            1,
        )

        after_original_completion = simulation.advance_to(10)
        self.assertEqual(
            after_original_completion["event_counts"][
                "PLANNED_MAINTENANCE_COMPLETED"
            ],
            1,
        )

    def test_planned_and_unplanned_downtime_are_counted_separately(self):
        simulation = ProductionLineSimulation(
            make_maintenance_scenario(
                raw_material_units=1,
                failure_probability=1,
            ),
            seed=7,
        )
        simulation.advance_to(6)
        simulation.start_preventive_maintenance("CNC-01")

        summary = simulation.advance_to(8)

        cnc = summary["machine_metrics"]["cnc_01"]
        self.assertEqual(cnc["failures"], 1)
        self.assertEqual(cnc["unplanned_downtime_minutes"], 5)
        self.assertEqual(cnc["down_minutes"], 5)
        self.assertEqual(cnc["planned_maintenance_minutes"], 2)
        self.assertEqual(cnc["maintenance_count"], 1)

    def test_availability_excludes_planned_maintenance_from_denominator(self):
        simulation = ProductionLineSimulation(
            make_maintenance_scenario(
                raw_material_units=1,
                failure_probability=1,
            ),
            seed=7,
        )
        simulation.advance_to(6)
        simulation.start_preventive_maintenance("CNC-01")

        summary = simulation.advance_to(10)

        cnc = summary["machine_metrics"]["cnc_01"]
        self.assertEqual(cnc["planned_maintenance_minutes"], 2)
        self.assertEqual(cnc["unplanned_downtime_minutes"], 5)
        self.assertEqual(cnc["availability"], 0.375)

        all_planned = ProductionLineSimulation(
            make_maintenance_scenario(
                raw_material_units=0,
                maintenance_duration=2,
            ),
            seed=7,
        )
        all_planned.start_preventive_maintenance("CNC-01")
        zero_denominator = all_planned.advance_to(1)
        self.assertEqual(
            zero_denominator["machine_metrics"]["cnc_01"]["availability"],
            0.0,
        )

    def test_session_charges_once_and_failed_repeat_changes_nothing(self):
        manager = SessionManager()
        scenario = make_maintenance_scenario(raw_material_units=0)
        with patch("plantops_sim.sessions.make_mvp_scenario", return_value=scenario):
            created = manager.create_session(seed=7)

        updated = manager.start_preventive_maintenance(
            created["session_id"],
            "CNC-01",
        )
        digest_after_success = updated["event_digest"]

        self.assertEqual(updated["preventive_maintenance_cost"], 250)
        self.assertEqual(updated["intervention_cost"], 0.0)
        with self.assertRaises(MachineCannotStartPreventiveMaintenanceError):
            manager.start_preventive_maintenance(created["session_id"], "CNC-01")
        unchanged = manager.get_session(created["session_id"])
        self.assertEqual(unchanged["preventive_maintenance_cost"], 250)
        self.assertEqual(unchanged["event_digest"], digest_after_success)

        completed = manager.advance_session(created["session_id"], 2)
        self.assertEqual(completed["preventive_maintenance_cost"], 250)

    def test_same_seed_and_maintenance_actions_remain_deterministic(self):
        scenario = make_maintenance_scenario(raw_material_units=5)
        first = ProductionLineSimulation(scenario, seed=17)
        second = ProductionLineSimulation(scenario, seed=17)

        for simulation in (first, second):
            simulation.start_preventive_maintenance("CNC-01")
            simulation.advance_to(12)

        self.assertEqual(first.summary(), second.summary())
        self.assertEqual(first.digest(), second.digest())


if __name__ == "__main__":
    unittest.main()
