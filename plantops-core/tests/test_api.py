from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

from plantops_sim import make_mvp_scenario
from plantops_sim.api import app


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()

    def test_health(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "service": "plantops-simulation"},
        )

    def test_simulate_returns_expected_result(self):
        response = self.client.post(
            "/simulate",
            json={"seed": 42, "minutes": 480, "failures_enabled": True},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("summary", payload)
        self.assertIn("event_digest", payload)
        self.assertIn("good_production", payload["summary"])
        self.assertIn("oee", payload["summary"])
        self.assertIn("machine_metrics", payload["summary"])
        self.assertIn("finished_goods_available", payload["summary"])
        self.assertIn("finished_goods_allocated", payload["summary"])
        self.assertIn("finished_goods_total", payload["summary"])
        self.assertIn("backlog_units", payload["summary"]["order_summary"])
        self.assertIn("backlog_orders", payload["summary"]["order_summary"])
        self.assertIn("supply_summary", payload["summary"])
        self.assertEqual(
            payload["summary"]["raw_material_remaining"],
            payload["summary"]["supply_summary"]["raw_material_on_hand"],
        )

    def test_same_request_returns_same_event_digest(self):
        request = {"seed": 42, "minutes": 480, "failures_enabled": True}

        first_response = self.client.post("/simulate", json=request)
        second_response = self.client.post("/simulate", json=request)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(
            first_response.json()["event_digest"],
            second_response.json()["event_digest"],
        )

    def create_session(self, **overrides):
        request = {"seed": 42, "failures_enabled": True, "speed": 1}
        request.update(overrides)
        response = self.client.post("/sessions", json=request)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def create_failed_session(self):
        forced_failure_scenario = make_mvp_scenario(
            raw_material_units=1,
            cnc_failure_probability=1.0,
        )
        with patch(
            "plantops_sim.sessions.make_mvp_scenario",
            return_value=forced_failure_scenario,
        ):
            session = self.create_session()

        response = self.client.post(
            f"/sessions/{session['session_id']}/advance",
            json={"minutes": 2},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["summary"]["machine_metrics"]["cnc_01"]["state"],
            "DOWN",
        )
        return response.json()

    def test_create_session_returns_uuid_and_initial_state(self):
        session = self.create_session()

        UUID(session["session_id"])
        self.assertFalse(session["paused"])
        self.assertEqual(session["speed"], 1)
        self.assertEqual(session["intervention_cost"], 0.0)
        self.assertEqual(session["preventive_maintenance_cost"], 0.0)
        self.assertEqual(session["summary"]["simulated_minutes"], 0)
        self.assertIn("order_summary", session["summary"])
        self.assertIn("finished_goods_available", session["summary"])
        self.assertIn("backlog_units", session["summary"]["order_summary"])
        self.assertIn("supply_summary", session["summary"])
        self.assertEqual(
            session["summary"]["raw_material_remaining"],
            session["summary"]["supply_summary"]["raw_material_on_hand"],
        )
        self.assertNotIn("simulation", session)

    def test_advance_changes_time_without_replacing_session(self):
        created = self.create_session()

        response = self.client.post(
            f"/sessions/{created['session_id']}/advance",
            json={"minutes": 15},
        )

        self.assertEqual(response.status_code, 200)
        advanced = response.json()
        self.assertEqual(advanced["session_id"], created["session_id"])
        self.assertEqual(advanced["summary"]["simulated_minutes"], 15)

        current = self.client.get(f"/sessions/{created['session_id']}").json()
        self.assertEqual(current["event_digest"], advanced["event_digest"])

    def test_pause_prevents_advance(self):
        session = self.create_session()
        session_id = session["session_id"]

        pause_response = self.client.post(f"/sessions/{session_id}/pause")
        advance_response = self.client.post(
            f"/sessions/{session_id}/advance",
            json={"minutes": 10},
        )

        self.assertEqual(pause_response.status_code, 200)
        self.assertTrue(pause_response.json()["paused"])
        self.assertEqual(advance_response.status_code, 409)
        self.assertEqual(
            self.client.get(f"/sessions/{session_id}").json()["summary"]["simulated_minutes"],
            0,
        )

    def test_resume_allows_advance_again(self):
        session_id = self.create_session()["session_id"]
        self.client.post(f"/sessions/{session_id}/pause")

        resume_response = self.client.post(f"/sessions/{session_id}/resume")
        advance_response = self.client.post(
            f"/sessions/{session_id}/advance",
            json={"minutes": 10},
        )

        self.assertEqual(resume_response.status_code, 200)
        self.assertFalse(resume_response.json()["paused"])
        self.assertEqual(advance_response.status_code, 200)
        self.assertEqual(advance_response.json()["summary"]["simulated_minutes"], 10)

    def test_invalid_speed_is_rejected(self):
        session_id = self.create_session()["session_id"]

        response = self.client.put(
            f"/sessions/{session_id}/speed",
            json={"speed": 3},
        )

        self.assertEqual(response.status_code, 422)

    def test_speed_can_be_changed(self):
        session_id = self.create_session()["session_id"]

        response = self.client.put(
            f"/sessions/{session_id}/speed",
            json={"speed": 4},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["speed"], 4)
        self.assertEqual(
            self.client.get(f"/sessions/{session_id}").json()["speed"],
            4,
        )

    def test_unknown_session_returns_not_found(self):
        unknown_session_id = "00000000-0000-0000-0000-000000000000"

        response = self.client.get(f"/sessions/{unknown_session_id}")

        self.assertEqual(response.status_code, 404)
        self.assertIn("was not found", response.json()["detail"])

    def test_same_seed_sessions_advance_independently_and_deterministically(self):
        first = self.create_session(seed=91)
        second = self.create_session(seed=91)

        first_advanced = self.client.post(
            f"/sessions/{first['session_id']}/advance",
            json={"minutes": 120},
        ).json()
        second_before_advance = self.client.get(
            f"/sessions/{second['session_id']}"
        ).json()
        second_advanced = self.client.post(
            f"/sessions/{second['session_id']}/advance",
            json={"minutes": 120},
        ).json()

        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertEqual(second_before_advance["summary"]["simulated_minutes"], 0)
        self.assertEqual(
            first_advanced["event_digest"],
            second_advanced["event_digest"],
        )
        self.assertEqual(first_advanced["summary"], second_advanced["summary"])

    def test_invalid_expedite_returns_conflict_without_cost(self):
        session = self.create_session()

        response = self.client.post(
            f"/sessions/{session['session_id']}/actions/expedite-repair",
            json={"machine_id": "CNC-01"},
        )

        self.assertEqual(response.status_code, 409)
        current = self.client.get(f"/sessions/{session['session_id']}").json()
        self.assertEqual(current["intervention_cost"], 0.0)
        self.assertEqual(current["event_digest"], session["event_digest"])

    def test_expedite_repair_adds_fixed_cost_once(self):
        session = self.create_failed_session()
        action_url = f"/sessions/{session['session_id']}/actions/expedite-repair"

        response = self.client.post(action_url, json={"machine_id": "CNC-01"})

        self.assertEqual(response.status_code, 200)
        updated = response.json()
        self.assertEqual(updated["intervention_cost"], 350.0)
        self.assertEqual(
            updated["summary"]["machine_metrics"]["cnc_01"]["state"],
            "IDLE",
        )

        duplicate_response = self.client.post(
            action_url,
            json={"machine_id": "CNC-01"},
        )
        self.assertEqual(duplicate_response.status_code, 409)
        self.assertEqual(
            self.client.get(f"/sessions/{session['session_id']}").json()[
                "intervention_cost"
            ],
            350.0,
        )

    def test_expedite_unknown_session_and_machine_return_not_found(self):
        unknown_session_id = "00000000-0000-0000-0000-000000000000"
        unknown_session_response = self.client.post(
            f"/sessions/{unknown_session_id}/actions/expedite-repair",
            json={"machine_id": "CNC-01"},
        )
        self.assertEqual(unknown_session_response.status_code, 404)

        session = self.create_session()
        unknown_machine_response = self.client.post(
            f"/sessions/{session['session_id']}/actions/expedite-repair",
            json={"machine_id": "UNKNOWN-01"},
        )
        self.assertEqual(unknown_machine_response.status_code, 404)
        current = self.client.get(f"/sessions/{session['session_id']}").json()
        self.assertEqual(current["intervention_cost"], 0.0)
        self.assertEqual(current["event_digest"], session["event_digest"])

    def test_paused_session_can_expedite_repair(self):
        session = self.create_failed_session()
        self.client.post(f"/sessions/{session['session_id']}/pause")

        response = self.client.post(
            f"/sessions/{session['session_id']}/actions/expedite-repair",
            json={"machine_id": "CNC-01"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["paused"])
        self.assertEqual(response.json()["intervention_cost"], 350.0)
        self.assertEqual(
            response.json()["summary"]["machine_metrics"]["cnc_01"]["state"],
            "IDLE",
        )

    def test_paused_session_can_reprioritize_without_changing_cost(self):
        session = self.create_session()
        session_id = session["session_id"]
        self.client.post(f"/sessions/{session_id}/pause")

        response = self.client.post(
            f"/sessions/{session_id}/actions/prioritize-order",
            json={"order_id": "ORDER-002", "priority": 100},
        )

        self.assertEqual(response.status_code, 200)
        updated = response.json()
        self.assertTrue(updated["paused"])
        self.assertEqual(updated["intervention_cost"], 0.0)
        order = next(
            order
            for order in updated["summary"]["order_summary"]["orders"]
            if order["id"] == "ORDER-002"
        )
        self.assertEqual(order["priority"], 100)
        self.assertEqual(
            updated["summary"]["event_counts"]["ORDER_PRIORITY_CHANGED"],
            1,
        )

    def test_reprioritize_unknown_session_and_order_return_not_found(self):
        unknown_session_id = "00000000-0000-0000-0000-000000000000"
        unknown_session_response = self.client.post(
            f"/sessions/{unknown_session_id}/actions/prioritize-order",
            json={"order_id": "ORDER-002", "priority": 100},
        )
        self.assertEqual(unknown_session_response.status_code, 404)

        session = self.create_session()
        unknown_order_response = self.client.post(
            f"/sessions/{session['session_id']}/actions/prioritize-order",
            json={"order_id": "UNKNOWN", "priority": 100},
        )
        self.assertEqual(unknown_order_response.status_code, 404)
        current = self.client.get(f"/sessions/{session['session_id']}").json()
        self.assertEqual(current["event_digest"], session["event_digest"])
        self.assertEqual(current["intervention_cost"], 0.0)

    def test_pending_and_completed_order_reprioritization_returns_conflict(self):
        session = self.create_session(failures_enabled=False)
        session_id = session["session_id"]

        pending_response = self.client.post(
            f"/sessions/{session_id}/actions/prioritize-order",
            json={"order_id": "ORDER-URGENT", "priority": 100},
        )
        self.assertEqual(pending_response.status_code, 409)
        after_pending = self.client.get(f"/sessions/{session_id}").json()
        self.assertEqual(after_pending["event_digest"], session["event_digest"])

        advance_response = self.client.post(
            f"/sessions/{session_id}/advance",
            json={"minutes": 150},
        )
        self.assertEqual(advance_response.status_code, 200)
        completed_response = self.client.post(
            f"/sessions/{session_id}/actions/prioritize-order",
            json={"order_id": "ORDER-001", "priority": 100},
        )
        self.assertEqual(completed_response.status_code, 409)
        current = self.client.get(f"/sessions/{session_id}").json()
        self.assertEqual(
            current["event_digest"],
            advance_response.json()["event_digest"],
        )

    def test_reprioritize_order_rejects_invalid_body_and_priority(self):
        session_id = self.create_session()["session_id"]

        for payload in (
            {},
            {"order_id": "", "priority": 50},
            {"order_id": "ORDER-002"},
            {"order_id": "ORDER-002", "priority": -1},
            {"order_id": "ORDER-002", "priority": 101},
            {"order_id": "ORDER-002", "priority": True},
            {"order_id": "ORDER-002", "priority": 1.5},
        ):
            with self.subTest(payload=payload):
                response = self.client.post(
                    f"/sessions/{session_id}/actions/prioritize-order",
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)

    def test_paused_session_can_place_purchase_order_without_intervention_cost(self):
        session = self.create_session()
        session_id = session["session_id"]
        raw_before = session["summary"]["raw_material_remaining"]
        self.client.post(f"/sessions/{session_id}/pause")

        response = self.client.post(
            f"/sessions/{session_id}/actions/place-purchase-order",
            json={"supplier_id": "STEEL-01", "quantity": 100},
        )

        self.assertEqual(response.status_code, 200)
        updated = response.json()
        supply = updated["summary"]["supply_summary"]
        self.assertTrue(updated["paused"])
        self.assertEqual(updated["intervention_cost"], 0.0)
        self.assertEqual(updated["summary"]["raw_material_remaining"], raw_before)
        self.assertEqual(supply["purchase_orders_total"], 1)
        self.assertEqual(supply["purchase_orders_open"], 1)
        self.assertEqual(supply["inbound_units"], 100)
        self.assertEqual(supply["received_units"], 0)
        self.assertEqual(supply["procurement_committed_cost"], 1_850.0)
        self.assertEqual(supply["purchase_orders"][0]["status"], "OPEN")
        self.assertIsNone(supply["purchase_orders"][0]["actual_receipt_minute"])

    def test_purchase_order_unknown_session_and_supplier_return_not_found(self):
        unknown_session_id = "00000000-0000-0000-0000-000000000000"
        unknown_session_response = self.client.post(
            f"/sessions/{unknown_session_id}/actions/place-purchase-order",
            json={"supplier_id": "STEEL-01", "quantity": 10},
        )
        self.assertEqual(unknown_session_response.status_code, 404)

        session = self.create_session()
        unknown_supplier_response = self.client.post(
            f"/sessions/{session['session_id']}/actions/place-purchase-order",
            json={"supplier_id": "UNKNOWN", "quantity": 10},
        )
        self.assertEqual(unknown_supplier_response.status_code, 404)
        current = self.client.get(f"/sessions/{session['session_id']}").json()
        self.assertEqual(current["event_digest"], session["event_digest"])
        self.assertEqual(current["summary"], session["summary"])

    def test_purchase_order_rejects_invalid_body_and_quantity(self):
        session_id = self.create_session()["session_id"]

        for payload in (
            {},
            {"supplier_id": "", "quantity": 10},
            {"supplier_id": "STEEL-01"},
            {"supplier_id": "STEEL-01", "quantity": 0},
            {"supplier_id": "STEEL-01", "quantity": -1},
            {"supplier_id": "STEEL-01", "quantity": 1_001},
            {"supplier_id": "STEEL-01", "quantity": True},
            {"supplier_id": "STEEL-01", "quantity": 1.5},
        ):
            with self.subTest(payload=payload):
                response = self.client.post(
                    f"/sessions/{session_id}/actions/place-purchase-order",
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)

    def test_paused_session_can_start_preventive_maintenance(self):
        session = self.create_session()
        session_id = session["session_id"]
        self.client.post(f"/sessions/{session_id}/pause")

        response = self.client.post(
            f"/sessions/{session_id}/actions/start-preventive-maintenance",
            json={"machine_id": "CNC-01"},
        )

        self.assertEqual(response.status_code, 200)
        updated = response.json()
        self.assertTrue(updated["paused"])
        self.assertEqual(updated["preventive_maintenance_cost"], 250.0)
        self.assertEqual(updated["intervention_cost"], 0.0)
        self.assertEqual(
            updated["summary"]["machine_metrics"]["cnc_01"]["state"],
            "PLANNED_MAINTENANCE",
        )

        duplicate = self.client.post(
            f"/sessions/{session_id}/actions/start-preventive-maintenance",
            json={"machine_id": "CNC-01"},
        )
        self.assertEqual(duplicate.status_code, 409)
        current = self.client.get(f"/sessions/{session_id}").json()
        self.assertEqual(current["preventive_maintenance_cost"], 250.0)
        self.assertEqual(current["event_digest"], updated["event_digest"])

    def test_preventive_maintenance_unknown_targets_return_not_found(self):
        unknown_session_id = "00000000-0000-0000-0000-000000000000"
        unknown_session = self.client.post(
            f"/sessions/{unknown_session_id}/actions/start-preventive-maintenance",
            json={"machine_id": "CNC-01"},
        )
        self.assertEqual(unknown_session.status_code, 404)

        session = self.create_session()
        unknown_machine = self.client.post(
            f"/sessions/{session['session_id']}/actions/start-preventive-maintenance",
            json={"machine_id": "UNKNOWN-01"},
        )
        self.assertEqual(unknown_machine.status_code, 404)
        current = self.client.get(f"/sessions/{session['session_id']}").json()
        self.assertEqual(current["preventive_maintenance_cost"], 0.0)
        self.assertEqual(current["event_digest"], session["event_digest"])

    def test_preventive_maintenance_rejects_running_and_down_machines(self):
        running_session = self.create_session()
        running_id = running_session["session_id"]
        self.client.post(
            f"/sessions/{running_id}/advance",
            json={"minutes": 0.1},
        )
        running_response = self.client.post(
            f"/sessions/{running_id}/actions/start-preventive-maintenance",
            json={"machine_id": "CNC-01"},
        )
        self.assertEqual(running_response.status_code, 409)
        self.assertEqual(
            self.client.get(f"/sessions/{running_id}").json()[
                "preventive_maintenance_cost"
            ],
            0.0,
        )

        down_session = self.create_failed_session()
        down_response = self.client.post(
            f"/sessions/{down_session['session_id']}/actions/start-preventive-maintenance",
            json={"machine_id": "CNC-01"},
        )
        self.assertEqual(down_response.status_code, 409)
        self.assertEqual(
            self.client.get(f"/sessions/{down_session['session_id']}").json()[
                "preventive_maintenance_cost"
            ],
            0.0,
        )

    def test_preventive_maintenance_rejects_invalid_body(self):
        session_id = self.create_session()["session_id"]

        for payload in ({}, {"machine_id": ""}):
            with self.subTest(payload=payload):
                response = self.client.post(
                    f"/sessions/{session_id}/actions/start-preventive-maintenance",
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)

    def test_expedite_repair_rejects_invalid_body(self):
        session_id = self.create_session()["session_id"]

        for payload in ({}, {"machine_id": ""}):
            with self.subTest(payload=payload):
                response = self.client.post(
                    f"/sessions/{session_id}/actions/expedite-repair",
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)

    def test_simulate_without_failures_reports_no_cnc_failures(self):
        response = self.client.post(
            "/simulate",
            json={"seed": 42, "minutes": 480, "failures_enabled": False},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["machine_metrics"]["cnc_01"]["failures"], 0)

    def test_simulate_rejects_invalid_request_limits(self):
        for payload in ({"seed": -1}, {"minutes": 0}, {"minutes": 10080.1}):
            with self.subTest(payload=payload):
                response = self.client.post("/simulate", json=payload)
                self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
