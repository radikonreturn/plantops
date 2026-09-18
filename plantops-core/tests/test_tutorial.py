from __future__ import annotations

import copy
import unittest

from fastapi.testclient import TestClient

from plantops_sim.api import app, session_manager
from plantops_sim.sessions import SessionManager


class TutorialTests(unittest.TestCase):
    def test_fixed_configuration_and_action_replay(self) -> None:
        results = []
        for seed in (0, 42, 999):
            manager = SessionManager()
            start = manager.create_session(seed=seed, scenario_mode="tutorial")
            sid = start["session_id"]
            self.assertEqual(start["summary"]["seed"], 0)
            self.assertTrue(start["paused"])
            self.assertEqual(start["shift_events"], [])
            self.assertEqual(start["summary"]["machine_metrics"]["laser_01"]["condition_value"], 65)
            manager.equipment_action(sid, "LASER-01", "clean-lens")
            manager.resume_session(sid)
            manager.advance_session(sid, 20)
            result = manager.get_session(sid)
            result.pop("session_id")
            results.append(result)
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])

    def test_real_service_time_cost_and_consequence(self) -> None:
        manager = SessionManager()
        first = manager.create_session(scenario_mode="tutorial")
        sid = first["session_id"]
        started = manager.equipment_action(sid, "laser_01", "clean-lens")
        self.assertEqual(started["cost_breakdown"]["lens_gas_cleaning"], 85)
        manager.resume_session(sid)
        midway = manager.advance_session(sid, 7)
        self.assertEqual(midway["summary"]["machine_metrics"]["laser_01"]["processed"], 0)
        finished = manager.advance_session(sid, 1)
        laser = finished["summary"]["machine_metrics"]["laser_01"]
        self.assertEqual(laser["condition_value"], 5)
        self.assertEqual(laser["planned_maintenance_minutes"], 8)
        self.assertEqual(laser["cycle_time_multiplier"], 1)
        self.assertTrue(any("normal cycles resume" in row["title"] for row in finished["timeline"]))
        manager.advance_session(sid, 42)
        serviced = manager.get_session(sid)
        other = manager.create_session(scenario_mode="tutorial")["session_id"]
        manager.resume_session(other)
        unserviced = manager.advance_session(other, 50)
        self.assertGreater(unserviced["summary"]["machine_metrics"]["laser_01"]["scrap"], 0)
        self.assertGreater(serviced["summary"]["good_production"], unserviced["summary"]["good_production"])
        self.assertEqual(unserviced["cost_breakdown"]["lens_gas_cleaning"], 0)

    def test_tutorial_is_quiet_and_snapshots_are_read_only(self) -> None:
        manager = SessionManager()
        sid = manager.create_session(scenario_mode="tutorial")["session_id"]
        sim = manager._sessions[sid].simulation
        sim.advance_to(20)
        before = copy.deepcopy((sim._events, sim.event_log, {k: v.getstate() for k, v in sim.rng._streams.items()}))
        self.assertEqual(manager.get_session(sid), manager.get_session(sid))
        self.assertEqual(before, (sim._events, sim.event_log, {k: v.getstate() for k, v in sim.rng._streams.items()}))
        sim.advance_to(60)
        self.assertTrue(all(e.zone == "laser_01" for e in sim.living.events.values()))
        self.assertEqual(list(sim.machines), ["laser_01", "cnc_01", "wash_01", "assembly_01", "test_01", "quality_01"])

    def test_other_modes_are_unaffected_by_tutorial_creation(self) -> None:
        manager = SessionManager()
        for mode in ("classic", "seeded"):
            before = manager.create_session(seed=9, scenario_mode=mode)
            manager.create_session(scenario_mode="tutorial")
            after = manager.create_session(seed=9, scenario_mode=mode)
            before.pop("session_id")
            after.pop("session_id")
            self.assertEqual(before, after)

    def test_invalid_requests_leave_sessions_and_costs_unchanged(self) -> None:
        with TestClient(app) as client:
            snapshot = client.post("/sessions", json={"scenario_mode": "tutorial"}).json()
            path = f"/sessions/{snapshot['session_id']}"
            count = len(session_manager._sessions)
            for body in ({"scenario_mode": "tutorial", "failures_enabled": False}, {"scenario_mode": "tutorial", "seed": -1}, {"scenario_mode": "tutorial", "speed": 3}):
                self.assertEqual(client.post("/sessions", json=body).status_code, 422)
            self.assertEqual(len(session_manager._sessions), count)
            self.assertEqual(client.post(path + "/actions/clean-lens", json={"machine_id": "wash_01"}).status_code, 409)
            self.assertEqual(client.post(path + "/actions/clean-lens", json={"machine_id": "laser_01", "cost": 0}).status_code, 422)
            self.assertEqual(client.get(path).json(), snapshot)
