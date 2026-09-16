from dataclasses import replace
import unittest

from fastapi.testclient import TestClient

from plantops_sim.api import app
from plantops_sim.engine import ProductionLineSimulation
from plantops_sim.scenario import make_mvp_scenario
from plantops_sim.profiles import PROFILE_DEFINITIONS, make_seeded_shift
from plantops_sim.engine import PreventiveMaintenanceNotConfiguredError, MachineCannotStartPreventiveMaintenanceError
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

    def test_decision_board_and_shift_review_are_state_backed_and_deterministic(self):
        first, second = self.create(), self.create()
        for snapshot in (first, second):
            profile = snapshot["scenario_profile"]
            self.assertEqual(len(profile["decision_cards"]), 3)
            self.assertEqual(profile["shift_review"]["state"], "interim")
            self.assertEqual(len(profile["shift_review"]["scorecard"]), 4)
            self.assertTrue(all(card["workspace"] for card in profile["decision_cards"]))
        self.assertEqual(first["scenario_profile"]["decision_cards"], second["scenario_profile"]["decision_cards"])
        self.manager.advance_session(first["session_id"], 480)
        finished = self.manager.get_session(first["session_id"])
        review = finished["scenario_profile"]["shift_review"]
        self.assertEqual(review["state"], "final")
        self.assertIn("Shift review", review["headline"])
        self.assertEqual(review["actions_recorded"], len(finished["action_log"]))

    def test_different_seeds_produce_materially_different_shifts(self):
        profiles = [self.create(seed)["scenario_profile"] for seed in range(80)]
        self.assertEqual(len({p["id"] for p in profiles}), 8)
        self.assertGreater(len({p["initial_conditions"]["raw_units"] for p in profiles}), 8)
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
        for seed, _, _ in self.profile_examples().values():
            session = self.create(seed, failures_enabled=False)
            updated = self.manager.advance_session(session["session_id"], 480)
            for metric in updated["summary"]["machine_metrics"].values():
                self.assertEqual(metric["failures"], 0)
            self.assertNotIn("MACHINE_FAILED", updated["summary"]["event_counts"])
            self.assertTrue(all(m["failure_risk"] == 0 for m in updated["scenario_profile"]["machines"]))

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

    def profile_examples(self):
        examples = {}
        for seed in range(100):
            scenario, profile = make_seeded_shift(make_mvp_scenario(), seed)
            examples.setdefault(profile.primary_zone, (seed, scenario, profile))
        self.assertEqual(len(examples), len(PROFILE_DEFINITIONS))
        return examples

    def test_expanded_route_and_buffer_metadata(self):
        snapshot = self.create()
        machines = snapshot["scenario_profile"]["machines"]
        ids = ["laser_01", "cnc_01", "wash_01", "assembly_01", "test_01", "quality_01"]
        self.assertEqual([m["id"] for m in machines], ids)
        route = ["raw"] + [f"after_{mid}" for mid in ids[:-1]] + ["finished"]
        self.assertEqual(list(snapshot["summary"]["buffer_levels"]), route)
        self.assertEqual([m["stage_role"] for m in machines], ["laser", "cnc", "wash", "assembly", "test", "quality"])
        for i, machine in enumerate(machines):
            self.assertEqual(machine["input_buffer"], route[i])
            self.assertEqual(machine["output_buffer"], route[i + 1])
            self.assertTrue(machine["name"])
            self.assertTrue(machine["fault_mode"])
        self.assertEqual([s.id for s in make_mvp_scenario().stages], ids[1:4] + ids[5:])

    def test_every_profile_drives_real_conditions_and_primary_alert(self):
        for zone, (seed, scenario, profile) in self.profile_examples().items():
            with self.subTest(profile=profile.id):
                snapshot = self.create(seed)
                projection = snapshot["scenario_profile"]
                self.assertEqual(projection["scene"]["highlighted_zone"], zone)
                self.assertEqual(projection["active_alerts"][0]["zone"], zone)
                definition = next(d for d in PROFILE_DEFINITIONS if d.zone == zone)
                if definition.queue_buffer:
                    self.assertGreaterEqual(dict(scenario.initial_wip)[definition.queue_buffer],
                                            scenario.buffer_capacities[definition.queue_buffer] - 2)
                if zone in {"laser_01", "cnc_01", "wash_01", "assembly_01", "test_01"}:
                    stage = next(s for s in scenario.stages if s.id == zone)
                    self.assertLess(stage.initial_health, 45)
                    machine = next(m for m in projection["machines"] if m["id"] == zone)
                    self.assertGreater(machine["failure_risk"], stage.failure_probability * 3)
                    self.assertTrue(machine["maintenance_available"])
                    if definition.cycle_minutes:
                        self.assertEqual(stage.ideal_cycle_minutes, definition.cycle_minutes)
                        self.assertIn(zone, projection["capacity"]["bottleneck_machines"])
                elif zone == "quality_01":
                    self.assertEqual(scenario.stages[-1].scrap_probability, 0.14)
                    self.assertEqual(snapshot["summary"]["scrap"], 0)
                    self.assertFalse(projection["machines"][-1]["maintenance_available"])
                elif zone == "raw":
                    self.assertLess(scenario.raw_material_units, 70)
                    self.assertEqual(scenario.suppliers[0].min_lead_minutes, 95)
                    self.assertGreater(projection["scene"]["receiving"]["uncovered_demand"], 0)
                else:
                    self.assertEqual(scenario.orders[0].due_minute, scenario.orders[1].due_minute)
                    self.assertGreater(projection["scene"]["dispatch"]["at_risk_orders"], 0)

    def test_all_profiles_replay_decisions_and_machine_metadata(self):
        for seed, _, _ in self.profile_examples().values():
            results = []
            for _ in range(2):
                session = self.create(seed)
                sid = session["session_id"]
                self.manager.start_preventive_maintenance(sid, "laser_01")
                self.manager.place_purchase_order(sid, "STEEL-01", 60)
                self.manager.advance_session(sid, 30)
                self.manager.reprioritize_order(sid, "ORDER-002", 99)
                results.append(self.manager.advance_session(sid, 450))
            for key in ("scenario_profile", "summary", "action_log", "event_digest"):
                self.assertEqual(results[0][key], results[1][key])

    def test_seeded_carry_in_and_multiple_receipts_never_reuse_ids(self):
        for seed, scenario, _ in self.profile_examples().values():
            sim = ProductionLineSimulation(scenario, seed=seed)
            initial_ids = [u for b in sim.buffers.values() for u in b.units]
            self.assertEqual(len(initial_ids), len(set(initial_ids)))
            last_initial = max(initial_ids)
            sim.place_purchase_order("STEEL-01", 8)
            sim.place_purchase_order("STEEL-01", 9)
            sim.advance_to(480)
            receipts = [e for e in sim.event_log if e.kind == "MATERIAL_RECEIVED"]
            received_ids = []
            for event in receipts:
                fields = dict(field.split("=", 1) for field in event.detail.split(";"))
                received_ids.extend(range(int(fields["first_unit_id"]), int(fields["last_unit_id"]) + 1))
            self.assertEqual(sorted(received_ids), list(range(last_initial + 1, last_initial + 18)))
            completed = [e.unit_id for e in sim.event_log if e.kind in {"FINISHED_GOODS_RECEIVED", "UNIT_SCRAPPED"}]
            self.assertEqual(len(completed), len(set(completed)))

    def test_each_configured_pm_consumes_time_cost_and_restores_health(self):
        for zone, (seed, _, _) in self.profile_examples().items():
            if zone not in {"laser_01", "cnc_01", "wash_01", "assembly_01", "test_01"}:
                continue
            with self.subTest(machine=zone):
                initial = self.create(seed)
                sid = initial["session_id"]
                config = next(m for m in initial["scenario_profile"]["machines"] if m["id"] == zone)
                started = self.manager.start_preventive_maintenance(sid, zone)
                self.assertEqual(started["preventive_maintenance_cost"], config["maintenance_cost"])
                self.assertEqual(started["summary"]["machine_metrics"][zone]["state"], "PLANNED_MAINTENANCE")
                with self.assertRaises(MachineCannotStartPreventiveMaintenanceError):
                    self.manager.start_preventive_maintenance(sid, zone)
                self.assertEqual(self.manager.get_session(sid), started)
                midway = self.manager.advance_session(sid, config["maintenance_duration"] / 2)
                metric = midway["summary"]["machine_metrics"][zone]
                self.assertEqual(metric["processed"], 0)
                self.assertEqual(metric["maintenance_count"], 0)
                finished = self.manager.advance_session(sid, config["maintenance_duration"] / 2)
                metric = finished["summary"]["machine_metrics"][zone]
                self.assertEqual(metric["health"], 100)
                self.assertEqual(metric["maintenance_count"], 1)
                self.assertEqual(metric["planned_maintenance_minutes"], config["maintenance_duration"])
                updated = next(m for m in finished["scenario_profile"]["machines"] if m["id"] == zone)
                self.assertLess(updated["failure_risk"], config["failure_risk"])
                self.assertEqual(updated["ideal_cycle_minutes"], config["ideal_cycle_minutes"])
                self.assertFalse(any(a["id"] == f"wear-{zone}" for a in finished["scenario_profile"]["active_alerts"]))
                self.assertEqual(len(finished["action_log"]), 1)

    def test_unavailable_pm_is_read_only_and_never_charged(self):
        session = self.create()
        sid = session["session_id"]
        with self.assertRaises(PreventiveMaintenanceNotConfiguredError):
            self.manager.start_preventive_maintenance(sid, "quality_01")
        self.assertEqual(self.manager.get_session(sid), session)

    def test_profile_alert_clears_with_actual_material_purchase(self):
        seed, _, _ = self.profile_examples()["raw"]
        session = self.create(seed)
        updated = self.manager.place_purchase_order(session["session_id"], "STEEL-01", 1000)
        self.assertFalse(any(a["id"] == "material-coverage" for a in updated["scenario_profile"]["active_alerts"]))
        self.assertEqual(updated["scenario_profile"]["scene"]["receiving"]["inbound_units"], 1000)
        self.assertEqual(updated["scenario_profile"]["scene"]["receiving"]["uncovered_demand"], 0)

    def test_quality_containment_rejects_real_units_at_final_inspection(self):
        seed, _, _ = self.profile_examples()["quality_01"]
        session = self.create(seed, failures_enabled=False)
        finished = self.manager.advance_session(session["session_id"], 480)
        summary = finished["summary"]
        self.assertGreater(summary["scrap"], 0)
        self.assertEqual(summary["scrap"], summary["machine_metrics"]["quality_01"]["scrap"])
        self.assertEqual(summary["good_production"] + summary["scrap"], summary["machine_metrics"]["quality_01"]["processed"])
        self.assertTrue(all(m["scrap"] == 0 for key, m in summary["machine_metrics"].items() if key != "quality_01"))

    def test_api_opt_in_profile_and_invalid_mode(self):
        with TestClient(app) as client:
            response = client.post("/sessions", json={"seed": 42, "scenario_mode": "seeded"})
            self.assertEqual(response.status_code, 200)
            self.assertNotEqual(response.json()["scenario_profile"]["id"], "classic-v1")
            self.assertEqual(client.post("/sessions", json={"scenario_mode": "invalid"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
