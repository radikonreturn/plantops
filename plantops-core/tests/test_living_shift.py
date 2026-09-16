from __future__ import annotations

import copy
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from plantops_sim.api import app
from plantops_sim.engine import ProductionLineSimulation, ShiftActionUnavailableError, UnknownPurchaseOrderError
from plantops_sim.sessions import SessionManager


class LivingShiftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = SessionManager()

    def create(self, seed: int = 9, **kwargs: Any) -> tuple[str, ProductionLineSimulation]:
        snapshot = self.manager.create_session(seed=seed, scenario_mode="seeded", **kwargs)
        return snapshot["session_id"], self.manager._sessions[snapshot["session_id"]].simulation

    def state(self, session_id: str) -> tuple[Any, ...]:
        sim = self.manager._sessions[session_id].simulation
        return (self.manager.get_session(session_id), copy.deepcopy(sim._events),
                {name: rng.getstate() for name, rng in sim.rng._streams.items()},
                copy.deepcopy(sim._cancelled_event_ids))

    def test_timeline_determinism_variation_and_profile_bias(self) -> None:
        signatures = set()
        for seed in range(24):
            first, a = self.create(seed)
            second, b = self.create(seed)
            self.assertEqual(a.living.snapshot(), b.living.snapshot())
            events = a.living.snapshot()["shift_events"]
            self.assertEqual(len(events), 3)
            self.assertEqual(len({e["id"] for e in events}), 3)
            signatures.add(tuple((e["minute"], e["kind"], e["zone"]) for e in events))
            zone = self.manager.get_session(first)["scenario_profile"]["primary_zone"]
            expected = {"raw": "supplier_delay", "dispatch": "customer_escalation", "quality_01": "quality_notice"}.get(zone, "condition_risk")
            self.assertEqual(events[0]["kind"], expected)
            self.assertEqual(self.manager.get_session(first)["timeline"], self.manager.get_session(second)["timeline"])
        self.assertGreater(len(signatures), 20)

    def test_snapshots_never_mutate_or_draw_rng(self) -> None:
        sid, sim = self.create()
        for minute in (0, 80, 220, 480):
            sim.advance_to(minute)
            before = self.state(sid)
            for _ in range(5):
                self.manager.get_session(sid)
                sim.summary()
            self.assertEqual(before, self.state(sid))

    def test_full_action_replay_including_final_review(self) -> None:
        def replay() -> tuple[dict[str, Any], list[Any]]:
            sid, sim = self.create()
            self.manager.living_action(sid, "containment")
            self.manager.living_action(sid, "overtime")
            self.manager.place_purchase_order(sid, "STEEL-01", 400)
            sim.advance_to(10)
            self.manager.living_action(sid, "expedite", "PO-000001")
            sim.advance_to(540)
            result = self.manager.get_session(sid)
            result.pop("session_id")
            return result, sim.event_log
        self.assertEqual(replay(), replay())

    def test_overtime_cost_boundary_and_real_production_time(self) -> None:
        sid, sim = self.create(42, failures_enabled=False)
        baseline_id, baseline = self.create(42, failures_enabled=False)
        for key in (sid, baseline_id):
            self.manager.place_purchase_order(key, "STEEL-01", 500)
        self.manager.living_action(sid, "overtime")
        sim.advance_to(479)
        baseline.advance_to(479)
        self.assertEqual(sim.summary()["good_production"], baseline.summary()["good_production"])
        self.assertFalse(sim.living.fatigue_active)
        sim.advance_to(480)
        self.assertTrue(sim.living.fatigue_active)
        sim.advance_to(900)
        baseline.advance_to(900)
        self.assertEqual(sim.clock, 540)
        self.assertEqual(baseline.clock, 480)
        self.assertGreater(sim.summary()["good_production"], baseline.summary()["good_production"])
        self.assertFalse(sim.living.fatigue_active)
        self.assertEqual(self.manager.get_session(sid)["cost_breakdown"]["overtime"], 600)

    def test_fatigue_multiplier_only_applies_during_overtime(self) -> None:
        sid, sim = self.create(42)
        sim.living.authorize_overtime()
        machine = sim.machines["cnc_01"]
        risk = sim.effective_failure_probability("cnc_01")
        sim.clock = 480  # Isolate the probability formula from production wear.
        self.assertAlmostEqual(sim.effective_failure_probability("cnc_01"), risk * 1.2)
        sim.clock = 540
        self.assertEqual(sim.effective_failure_probability("cnc_01"), risk)
        self.assertEqual(machine.health, machine.config.initial_health)

    def test_duplicate_and_unavailable_actions_are_atomic(self) -> None:
        sid, sim = self.create(42)
        for action, po, error in (("containment", "", ShiftActionUnavailableError), ("expedite", "missing", UnknownPurchaseOrderError)):
            before = self.state(sid)
            with self.assertRaises(error):
                self.manager.living_action(sid, action, po)
            self.assertEqual(before, self.state(sid))
        self.manager.living_action(sid, "overtime")
        before = self.state(sid)
        with self.assertRaises(ShiftActionUnavailableError):
            self.manager.living_action(sid, "overtime")
        self.assertEqual(before, self.state(sid))
        sim.advance_to(540)
        before = self.state(sid)
        with self.assertRaises(ShiftActionUnavailableError):
            self.manager.place_purchase_order(sid, "STEEL-01", 20)
        self.assertEqual(before, self.state(sid))

    def test_expedite_only_target_po_charges_once_and_cancels_old_receipt(self) -> None:
        sid, sim = self.create(42)
        for _ in range(2):
            self.manager.place_purchase_order(sid, "STEEL-01", 10)
        original = dict(sim.living.receipt_times)
        self.manager.living_action(sid, "expedite", "PO-000001")
        self.assertEqual(sim.living.receipt_times["PO-000001"], original["PO-000001"] / 2)
        self.assertEqual(sim.living.receipt_times["PO-000002"], original["PO-000002"])
        before = self.state(sid)
        with self.assertRaises(ShiftActionUnavailableError):
            self.manager.living_action(sid, "expedite", "PO-000001")
        self.assertEqual(before, self.state(sid))
        sim.advance_to(200)
        self.assertEqual(sum(e.kind == "MATERIAL_RECEIVED" for e in sim.event_log), 2)
        before = self.state(sid)
        with self.assertRaises(ShiftActionUnavailableError):
            self.manager.living_action(sid, "expedite", "PO-000002")
        self.assertEqual(before, self.state(sid))
        self.assertEqual(self.manager.get_session(sid)["cost_breakdown"]["expediting"], 120)

    def test_containment_captures_real_defects_adds_work_and_preserves_source_risk(self) -> None:
        sid, sim = self.create()
        other_id, other = self.create()
        probability = sim.machines["quality_01"].config.scrap_probability
        self.manager.living_action(sid, "containment")
        before = self.state(sid)
        with self.assertRaises(ShiftActionUnavailableError):
            self.manager.living_action(sid, "containment")
        self.assertEqual(before, self.state(sid))
        for key in (sid, other_id):
            self.manager.place_purchase_order(key, "STEEL-01", 300)
        sim.advance_to(480)
        other.advance_to(480)
        q = sim.living.snapshot()["quality_containment"]
        self.assertGreater(q["captured_units"], 0)
        self.assertEqual(q["customer_escapes"], 0)
        self.assertGreater(other.living.snapshot()["quality_containment"]["customer_escapes"], 0)
        self.assertEqual(q["inspection_cost"], q["inspected_units"] * 2)
        self.assertAlmostEqual(q["added_inspection_minutes"], q["inspected_units"] * .6)
        self.assertEqual(sim.machines["quality_01"].config.scrap_probability, probability)
        self.assertEqual(q["captured_units"], sum(e.kind == "LATENT_DEFECT_CONTAINED" for e in sim.event_log))
        self.assertLessEqual(q["captured_units"], sim.summary()["scrap"])

    def test_quality_inflight_cycle_is_not_retroactively_contained(self) -> None:
        sid, sim = self.create()
        sim.advance_to(.01)
        # A cycle started without inspection retains that disposition after activation.
        sim.living.activate_containment()
        self.assertEqual(sim.living.inspected_units, 0)
        self.assertEqual(sim.living.inspection_units, set())

    def test_events_change_real_state_and_expire(self) -> None:
        sid, sim = self.create(2)
        event = next(e for e in sim.living.events.values() if e.kind == "supplier_delay")
        sim.advance_to(event.minute)
        self.assertEqual(event.state, "active")
        po = sim.place_purchase_order("STEEL-01", 20)
        self.assertIn(po.id, event.affected_ids)
        self.assertGreaterEqual(sim.living.receipt_times[po.id], po.promised_receipt_minute + 25)
        sim.advance_to(480)
        self.assertEqual(event.state, "resolved")
        self.assertTrue(all(e.state in {"resolved", "expired"} for e in sim.living.events.values()))

    def test_condition_event_can_be_resolved_by_actual_service(self) -> None:
        sid, sim = self.create(42)
        event = next(e for e in sim.living.events.values() if e.kind == "condition_risk")
        machine = sim.machines[event.zone]
        before = machine.health
        # A stationary fixture makes the event's health delta independently measurable.
        for buffer in sim.buffers.values():
            buffer.units.clear()
        sim.advance_to(event.minute)
        self.assertEqual(machine.health, before - 18)
        self.manager.start_preventive_maintenance(sid, event.zone)
        sim.advance_to(event.minute + machine.config.preventive_maintenance_duration)
        self.assertEqual(event.state, "resolved")

    def test_review_cards_costs_timeline_match_actions(self) -> None:
        sid, sim = self.create()
        self.manager.living_action(sid, "containment")
        self.manager.living_action(sid, "overtime")
        snapshot = self.manager.get_session(sid)
        cards = snapshot["scenario_profile"]["decision_cards"]
        self.assertLessEqual(len(cards), 3)
        self.assertTrue(next(c for c in cards if c["id"] == "contain-quality")["decision_logged"])
        self.assertTrue(next(c for c in cards if c["id"] == "shift-extension")["decision_logged"])
        self.assertTrue(any(t["title"] == "overtime authorized" for t in snapshot["timeline"]))
        sim.advance_to(480)
        self.assertEqual(self.manager.get_session(sid)["scenario_profile"]["shift_review"]["state"], "interim")
        sim.advance_to(540)
        snapshot = self.manager.get_session(sid)
        review = snapshot["scenario_profile"]["shift_review"]
        self.assertEqual(review["state"], "final")
        self.assertEqual(review["event_history"], snapshot["shift_events"])
        self.assertEqual(review["actions_recorded"], len(snapshot["action_log"]))
        self.assertEqual(review["cost_breakdown"], snapshot["cost_breakdown"])
        self.assertEqual(snapshot["cost_breakdown"]["total"], sum(v for k,v in snapshot["cost_breakdown"].items() if k != "total"))

    def test_event_schedule_draws_do_not_change_existing_rng_streams(self) -> None:
        from plantops_sim.profiles import make_seeded_shift
        from plantops_sim.scenario import make_mvp_scenario

        _, sim = self.create(42)
        scenario, _ = make_seeded_shift(make_mvp_scenario(), 42)
        baseline = ProductionLineSimulation(scenario, seed=42)
        for name, rng in baseline.rng._streams.items():
            self.assertEqual(rng.getstate(), sim.rng._streams[name].getstate())
        self.assertEqual(sim.rng._streams.keys() - baseline.rng._streams.keys(), {"shift-events:v1"})

    def test_operator_shortage_changes_only_target_cycles_during_window(self) -> None:
        _, sim = self.create(42)
        event = next((e for e in sim.living.events.values() if e.kind == "operator_shortage"), None)
        if event is None:
            for seed in range(30):
                _, sim = self.create(seed)
                event = next((e for e in sim.living.events.values() if e.kind == "operator_shortage"), None)
                if event:
                    break
        self.assertIsNotNone(event)
        self.assertEqual(sim.living.cycle_minutes(event.zone, 1, 2), 2)
        sim.clock = event.minute
        sim.living.handle_event("SHIFT_EVENT_START", event.id)
        self.assertAlmostEqual(sim.living.cycle_minutes(event.zone, 1, 2), 2.8)
        self.assertEqual(sim.living.cycle_minutes("unaffected", 1, 2), 2)
        sim.clock = event.end_minute
        sim.living.handle_event("SHIFT_EVENT_END", event.id)
        self.assertEqual(sim.living.cycle_minutes(event.zone, 1, 2), 2)
        self.assertEqual(event.state, "expired")

    def test_seeded_incremental_advances_match_single_advance(self) -> None:
        first, a = self.create()
        second, b = self.create()
        for sid in (first, second):
            self.manager.living_action(sid, "containment")
            self.manager.living_action(sid, "overtime")
        for minute in range(1, 541):
            a.advance_to(minute)
        b.advance_to(540)
        self.assertEqual(a.summary(), b.summary())
        self.assertEqual(a.event_log, b.event_log)
        self.assertEqual(a.digest(), b.digest())

    def test_frontend_does_not_use_math_random(self) -> None:
        for path in (Path(__file__).parents[2] / "plantops-web/src").rglob("*"):
            if path.suffix in {".ts", ".tsx"}:
                self.assertNotIn("Math.random", path.read_text(), str(path))


class LivingShiftApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)

    def test_api_validation_and_rejections_do_not_mutate(self) -> None:
        snapshot = self.client.post("/sessions", json={"seed": 42, "scenario_mode": "seeded"}).json()
        sid = snapshot["session_id"]
        for action, body, expected in [
            ("authorize-overtime", {"minutes": 99}, 422),
            ("expedite-purchase-order", {}, 422),
            ("expedite-purchase-order", {"purchase_order_id": 5}, 422),
            ("expedite-purchase-order", {"purchase_order_id": "missing"}, 404),
            ("activate-containment", {}, 409),
        ]:
            with self.subTest(action=action, body=body):
                response = self.client.post(f"/sessions/{sid}/actions/{action}", json=body)
                self.assertEqual(response.status_code, expected)
                self.assertEqual(snapshot, self.client.get(f"/sessions/{sid}").json())
        url = f"/sessions/{sid}/actions/authorize-overtime"
        self.assertEqual(self.client.post(url, json={}).status_code, 200)
        before = self.client.get(f"/sessions/{sid}").json()
        self.assertEqual(self.client.post(url, json={}).status_code, 409)
        self.assertEqual(before, self.client.get(f"/sessions/{sid}").json())
        self.assertEqual(self.client.post("/sessions/missing/actions/authorize-overtime", json={}).status_code, 404)

    def test_api_successful_quality_and_expedite_and_closed_shift(self) -> None:
        snapshot = self.client.post("/sessions", json={"seed": 9, "scenario_mode": "seeded"}).json()
        path = f"/sessions/{snapshot['session_id']}"
        self.assertEqual(self.client.post(path + "/actions/activate-containment", json={}).status_code, 200)
        self.assertEqual(self.client.post(path + "/actions/place-purchase-order", json={"supplier_id": "STEEL-01", "quantity": 20}).status_code, 200)
        expedite = path + "/actions/expedite-purchase-order"
        self.assertEqual(self.client.post(expedite, json={"purchase_order_id": "PO-000001"}).status_code, 200)
        self.assertEqual(self.client.post(expedite, json={"purchase_order_id": "PO-000001"}).status_code, 409)
        closed = self.client.post(path + "/advance", json={"minutes": 600}).json()
        self.assertEqual(closed["summary"]["simulated_minutes"], 480)
        self.assertEqual(self.client.post(path + "/actions/authorize-overtime", json={}).status_code, 409)
        self.assertEqual(closed, self.client.get(path).json())

    def test_classic_rejects_v3_without_mutation(self) -> None:
        snapshot = self.client.post("/sessions", json={}).json()
        path = f"/sessions/{snapshot['session_id']}"
        self.assertEqual(self.client.post(path + "/actions/authorize-overtime", json={}).status_code, 409)
        self.assertEqual(snapshot, self.client.get(path).json())
