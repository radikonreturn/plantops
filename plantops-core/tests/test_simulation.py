from __future__ import annotations

import unittest

from plantops_sim import ProductionLineSimulation, make_mvp_scenario
from plantops_sim.engine import MachineNotDownError, UnknownMachineError


class ProductionLineSimulationTests(unittest.TestCase):
    def run_simulation(self, seed: int, **kwargs):
        scenario = make_mvp_scenario(**kwargs)
        simulation = ProductionLineSimulation(scenario, seed=seed)
        return simulation, simulation.run()

    def make_failed_simulation(self, raw_material_units: int = 1):
        scenario = make_mvp_scenario(
            raw_material_units=raw_material_units,
            cnc_failure_probability=1.0,
        )
        simulation = ProductionLineSimulation(scenario, seed=42)
        simulation.advance_to(2)
        self.assertEqual(simulation.summary()["machine_metrics"]["cnc_01"]["state"], "DOWN")
        return simulation

    def test_same_seed_produces_same_summary_and_event_digest(self):
        first, first_result = self.run_simulation(77)
        second, second_result = self.run_simulation(77)
        self.assertEqual(first_result, second_result)
        self.assertEqual(first.digest(), second.digest())

    def test_different_seed_changes_event_stream(self):
        first, _ = self.run_simulation(11)
        second, _ = self.run_simulation(12)
        self.assertNotEqual(first.digest(), second.digest())

    def test_line_produces_good_units(self):
        _, result = self.run_simulation(42, cnc_failure_probability=0)
        self.assertGreater(result["good_production"], 0)
        self.assertLessEqual(result["good_production"] + result["scrap"], 500)

    def test_forced_machine_failures_create_downtime(self):
        sim, result = self.run_simulation(42, cnc_failure_probability=1.0)
        cnc = result["machine_metrics"]["cnc_01"]
        self.assertGreater(cnc["failures"], 0)
        self.assertGreater(cnc["down_minutes"], 0)
        self.assertIn("MACHINE_FAILED", result["event_counts"])
        self.assertTrue(any(event.kind == "REPAIR_COMPLETED" for event in sim.event_log))

    def test_unfinished_repair_counts_as_downtime_at_shift_end(self):
        scenario = make_mvp_scenario(cnc_failure_probability=1.0)
        sim = ProductionLineSimulation(scenario, seed=42)
        result = sim.run(2)
        cnc = result["machine_metrics"]["cnc_01"]

        self.assertEqual(cnc["state"], "DOWN")
        self.assertGreater(cnc["down_minutes"], 0)
        self.assertLess(cnc["availability"], 1)

    def test_small_buffers_can_block_upstream_machine(self):
        scenario = make_mvp_scenario(cnc_failure_probability=0)
        scenario.buffer_capacities["after_cnc_01"] = 1
        sim = ProductionLineSimulation(scenario, seed=9)
        sim.run(60)
        self.assertTrue(any(event.kind == "MACHINE_BLOCKED" for event in sim.event_log))

    def test_empty_raw_material_eventually_starves_first_machine(self):
        scenario = make_mvp_scenario(raw_material_units=2, cnc_failure_probability=0)
        sim = ProductionLineSimulation(scenario, seed=4)
        sim.run(60)
        self.assertTrue(any(event.kind == "MACHINE_STARVED" and event.machine_id == "cnc_01" for event in sim.event_log))

    def test_quality_is_calculated_from_good_and_total_quality_units(self):
        _, result = self.run_simulation(2, cnc_failure_probability=0)
        quality = result["quality"]
        self.assertGreaterEqual(quality, 0)
        self.assertLessEqual(quality, 1)
        self.assertGreater(result["oee"], 0)

    def test_incremental_advance_matches_single_run(self):
        incremental = ProductionLineSimulation(make_mvp_scenario(), seed=77)
        incremental.advance_to(120)
        incremental.advance_by(180)
        incremental_result = incremental.run(480)

        single_run = ProductionLineSimulation(make_mvp_scenario(), seed=77)
        single_run_result = single_run.run(480)

        self.assertEqual(incremental_result, single_run_result)
        self.assertEqual(incremental.digest(), single_run.digest())

    def test_incremental_advance_rejects_backwards_time(self):
        simulation = ProductionLineSimulation(make_mvp_scenario(), seed=42)
        simulation.advance_to(60)

        with self.assertRaisesRegex(ValueError, "backwards"):
            simulation.advance_to(59)

    def test_incremental_updates_do_not_add_completion_events(self):
        simulation = ProductionLineSimulation(make_mvp_scenario(), seed=42)
        simulation.advance_by(30)
        simulation.advance_by(30)

        self.assertNotIn("SIMULATION_COMPLETED", simulation.summary()["event_counts"])

        simulation.run(90)
        simulation.run(90)
        self.assertEqual(simulation.summary()["event_counts"]["SIMULATION_COMPLETED"], 1)

    def test_expedited_repair_returns_failed_machine_to_service_immediately(self):
        simulation = self.make_failed_simulation(raw_material_units=2)
        clock_before_action = simulation.clock

        simulation.expedite_repair("CNC-01")

        cnc = simulation.summary()["machine_metrics"]["cnc_01"]
        self.assertEqual(simulation.clock, clock_before_action)
        self.assertEqual(cnc["state"], "IDLE")
        self.assertGreater(cnc["down_minutes"], 0)
        self.assertEqual(simulation.event_log[-2].kind, "REPAIR_EXPEDITED")
        self.assertEqual(simulation.event_log[-1].kind, "REPAIR_COMPLETED")

        simulation.advance_by(0.1)
        self.assertEqual(
            simulation.summary()["machine_metrics"]["cnc_01"]["state"],
            "RUNNING",
        )

    def test_expedited_repair_cancels_original_repair_completion(self):
        simulation = self.make_failed_simulation()
        simulation.expedite_repair("CNC-01")
        expedited_downtime = simulation.summary()["machine_metrics"]["cnc_01"][
            "down_minutes"
        ]

        simulation.advance_to(30)

        event_counts = simulation.summary()["event_counts"]
        self.assertEqual(event_counts["REPAIR_EXPEDITED"], 1)
        self.assertEqual(event_counts["REPAIR_COMPLETED"], 1)

        ordinary_repair = self.make_failed_simulation()
        ordinary_repair.advance_to(30)
        ordinary_downtime = ordinary_repair.summary()["machine_metrics"]["cnc_01"][
            "down_minutes"
        ]
        self.assertLess(expedited_downtime, ordinary_downtime)

    def test_invalid_expedite_attempts_do_not_change_state(self):
        simulation = ProductionLineSimulation(make_mvp_scenario(), seed=42)
        summary_before = simulation.summary()
        digest_before = simulation.digest()

        with self.assertRaisesRegex(UnknownMachineError, "was not found"):
            simulation.expedite_repair("UNKNOWN-01")
        with self.assertRaisesRegex(MachineNotDownError, "not DOWN"):
            simulation.expedite_repair("CNC-01")

        self.assertEqual(simulation.summary(), summary_before)
        self.assertEqual(simulation.digest(), digest_before)

    def test_no_intervention_preserves_reference_digest(self):
        simulation = ProductionLineSimulation(make_mvp_scenario(), seed=42)
        simulation.run(480)

        self.assertEqual(
            simulation.digest(),
            "a0b13826abaddf740ff0f86b5b517b4c58343d2166046230de820e760234615a",
        )


if __name__ == "__main__":
    unittest.main()
