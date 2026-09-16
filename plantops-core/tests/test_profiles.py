from dataclasses import replace
import unittest

from fastapi.testclient import TestClient

from plantops_sim.api import app
from plantops_sim.engine import ProductionLineSimulation
from plantops_sim.scenario import make_mvp_scenario
from plantops_sim.sessions import SessionManager


class ScenarioProfileTests(unittest.TestCase):
    def setUp(self):
        self.manager = SessionManager()

    def create(self, seed=42, **kwargs):
        return self.manager.create_session(seed=seed, scenario_mode="seeded", **kwargs)

    def test_same_seed_replays_profile_scene_alerts_summary_and_digest(self):
        first, second = self.create(), self.create()
        for minutes in (0, 10, 120, 350):
            if minutes:
                first = self.manager.advance_session(first["session_id"], minutes)
                second = self.manager.advance_session(second["session_id"], minutes)
            for key in ("scenario_profile", "summary", "event_digest", "action_log"):
                self.assertEqual(first[key], second[key])

    def test_different_seeds_produce_materially_different_shifts(self):
        profiles = [self.create(seed)["scenario_profile"] for seed in range(20)]
        self.assertEqual(len({p["id"] for p in profiles}), 5)
        self.assertGreater(len({p["initial_conditions"]["raw_units"] for p in profiles}), 5)
        self.assertGreater(len({p["briefing"] for p in profiles}), 1)
        self.assertNotEqual(profiles[0]["scene"], profiles[1]["scene"])
        self.assertNotEqual(profiles[0]["active_alerts"], profiles[1]["active_alerts"])

    def test_classic_session_keeps_original_summary_and_digest(self):
        session = self.manager.create_session(seed=42)
        original = ProductionLineSimulation(make_mvp_scenario(), seed=42)
        self.assertEqual(session["summary"], original.summary())
        self.assertEqual(session["event_digest"], original.digest())
        session = self.manager.advance_session(session["session_id"], 480)
        self.assertEqual(session["summary"], original.advance_to(480))
        self.assertEqual(session["event_digest"], original.digest())

    def test_snapshot_is_read_only_and_scene_matches_stock(self):
        session = self.create()
        for minutes in (0, 25, 300):
            if minutes:
                session = self.manager.advance_session(session["session_id"], minutes)
            self.assertEqual(session, self.manager.get_session(session["session_id"]))
            for zone in session["scenario_profile"]["scene"]["zones"]:
                expected = (session["summary"]["finished_goods_available"] if zone["id"] == "finished"
                            else session["summary"]["buffer_levels"][zone["id"]])
                self.assertEqual(zone["units"], expected)
                self.assertEqual(zone["pallets"], (expected + zone["units_per_pallet"] - 1) // zone["units_per_pallet"])

    def test_carry_in_wip_and_receipt_unit_ids_do_not_collide(self):
        base = make_mvp_scenario(raw_material_units=3, cnc_failure_probability=0)
        scenario = replace(base, initial_wip=(("after_cnc_01", 2), ("after_wash_01", 1)))
        sim = ProductionLineSimulation(scenario, seed=4)
        self.assertEqual(sim.summary()["wip"], 3)
        ids = [u for b in sim.buffers.values() for u in b.units]
        self.assertEqual(sorted(ids), list(range(1, 7)))
        sim.place_purchase_order("STEEL-01", 5)
        sim.advance_to(480)
        received = next(e for e in sim.event_log if e.kind == "MATERIAL_RECEIVED")
        self.assertIn("first_unit_id=7;last_unit_id=11", received.detail)
        self.assertEqual(sim.summary()["good_production"] + sim.summary()["scrap"], 11)

    def test_initial_conditions_are_validated(self):
        base = make_mvp_scenario()
        for initial_wip in ((("raw", 2),), (("after_cnc_01", 19),), (("missing", 1),),
                            (("after_cnc_01", 1), ("after_cnc_01", 2))):
            with self.assertRaises(ValueError):
                replace(base, initial_wip=initial_wip)
        for health in (-1, 101, float("nan"), True):
            with self.assertRaises(ValueError):
                replace(base.stages[0], initial_health=health)

    def test_disabled_failures_remain_zero_in_seeded_profiles(self):
        for seed in range(10):
            session = self.create(seed, failures_enabled=False)
            updated = self.manager.advance_session(session["session_id"], 480)
            self.assertEqual(updated["summary"]["machine_metrics"]["cnc_01"]["failures"], 0)

    def test_real_actions_are_logged_once_and_replay_deterministically(self):
        snapshots = []
        for _ in range(2):
            session = self.create()
            sid = session["session_id"]
            self.manager.pause_session(sid)
            self.manager.start_preventive_maintenance(sid, "CNC-01")
            self.manager.reprioritize_order(sid, "ORDER-001", 100)
            self.manager.reprioritize_order(sid, "ORDER-001", 100)
            session = self.manager.place_purchase_order(sid, "STEEL-01", 100)
            self.assertEqual(len(session["action_log"]), 3)
            self.assertEqual(session["preventive_maintenance_cost"], 250)
            self.manager.resume_session(sid)
            snapshots.append(self.manager.advance_session(sid, 160))
        for key in ("summary", "event_digest", "action_log", "scenario_profile"):
            self.assertEqual(snapshots[0][key], snapshots[1][key])

    def test_api_opt_in_profile_and_invalid_mode(self):
        with TestClient(app) as client:
            response = client.post("/sessions", json={"seed": 42, "scenario_mode": "seeded"})
            self.assertEqual(response.status_code, 200)
            self.assertNotEqual(response.json()["scenario_profile"]["id"], "classic-v1")
            self.assertEqual(client.post("/sessions", json={"scenario_mode": "invalid"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
