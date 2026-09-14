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


if __name__ == "__main__":
    unittest.main()
