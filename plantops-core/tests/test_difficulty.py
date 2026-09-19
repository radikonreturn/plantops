from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from plantops_sim.api import app
from plantops_sim.sessions import SessionManager


class DifficultyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = SessionManager()

    def create(self, difficulty: str):
        return self.manager.create_session(
            seed=42, scenario_mode="seeded", difficulty=difficulty
        )

    def test_difficulty_changes_real_operating_conditions(self) -> None:
        easy = self.create("easy")
        normal = self.create("normal")
        hard = self.create("hard")

        self.assertEqual(easy["difficulty"], "easy")
        self.assertEqual(normal["difficulty"], "normal")
        self.assertEqual(hard["difficulty"], "hard")
        self.assertGreater(
            easy["summary"]["raw_material_remaining"],
            normal["summary"]["raw_material_remaining"],
        )
        self.assertGreater(
            normal["summary"]["raw_material_remaining"],
            hard["summary"]["raw_material_remaining"],
        )
        self.assertLess(
            easy["summary"]["order_summary"]["units_ordered"],
            hard["summary"]["order_summary"]["units_ordered"],
        )
        self.assertGreater(
            min(easy["scenario_profile"]["initial_conditions"]["machine_health"].values()),
            min(hard["scenario_profile"]["initial_conditions"]["machine_health"].values()),
        )

    def test_same_seed_and_difficulty_replay_exactly(self) -> None:
        for difficulty in ("easy", "normal", "hard"):
            first = self.create(difficulty)
            second = self.create(difficulty)
            first = self.manager.advance_session(first["session_id"], 180)
            second = self.manager.advance_session(second["session_id"], 180)
            for key in ("summary", "scenario_profile", "event_digest"):
                self.assertEqual(first[key], second[key])

    def test_tutorial_has_fixed_guided_difficulty(self) -> None:
        tutorial = self.manager.create_session(
            seed=999, scenario_mode="tutorial", difficulty="hard"
        )
        self.assertEqual(tutorial["difficulty"], "easy")

    def test_api_rejects_unknown_difficulty(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/sessions",
                json={"seed": 42, "scenario_mode": "seeded", "difficulty": "nightmare"},
            )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
