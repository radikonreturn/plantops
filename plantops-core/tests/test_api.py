from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

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
