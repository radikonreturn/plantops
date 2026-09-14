from __future__ import annotations

import unittest

from pydantic import ValidationError

from plantops_sim.api import SimulationRequest, app, health, simulate


class ApiTests(unittest.TestCase):
    def test_app_metadata_and_health(self):
        self.assertEqual(app.title, "PlantOps API")
        self.assertEqual(app.version, "0.1.0")
        self.assertIn("get", app.openapi()["paths"]["/health"])
        self.assertIn("post", app.openapi()["paths"]["/simulate"])
        self.assertEqual(
            health(),
            {"status": "ok", "service": "plantops-simulation"},
        )

    def test_simulate_without_failures(self):
        payload = simulate(
            SimulationRequest(seed=42, minutes=60, failures_enabled=False)
        )

        self.assertEqual(payload["summary"]["seed"], 42)
        self.assertEqual(payload["summary"]["simulated_minutes"], 60)
        self.assertEqual(payload["summary"]["machine_metrics"]["cnc_01"]["failures"], 0)
        self.assertEqual(len(payload["event_digest"]), 64)

    def test_request_defaults(self):
        request = SimulationRequest()

        self.assertEqual(request.seed, 42)
        self.assertEqual(request.minutes, 480)
        self.assertTrue(request.failures_enabled)

    def test_request_limits(self):
        invalid_payloads = (
            {"seed": -1},
            {"minutes": 0},
            {"minutes": 10080.1},
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                SimulationRequest(**payload)


if __name__ == "__main__":
    unittest.main()
