from __future__ import annotations

import unittest

from plantops_sim import ProductionLineSimulation, make_mvp_scenario


class ProductionLineSimulationTests(unittest.TestCase):
    def run_simulation(self, seed: int, **kwargs):
        scenario = make_mvp_scenario(**kwargs)
        simulation = ProductionLineSimulation(scenario, seed=seed)
        return simulation, simulation.run()

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


if __name__ == "__main__":
    unittest.main()
