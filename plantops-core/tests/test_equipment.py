from __future__ import annotations

import copy
from dataclasses import replace
import unittest
from typing import Any

from fastapi.testclient import TestClient

from plantops_sim.api import app, session_manager
from plantops_sim.engine import ProductionLineSimulation, ShiftActionUnavailableError
from plantops_sim.equipment import SPECS
from plantops_sim.living import LivingShift
from plantops_sim.scenario import make_mvp_scenario, make_seeded_line
from plantops_sim.sessions import SessionManager


class EquipmentTests(unittest.TestCase):
    def controlled(self) -> ProductionLineSimulation:
        line = make_seeded_line(make_mvp_scenario(raw_material_units=300))
        line = replace(line, stages=tuple(replace(
            stage, initial_health=100, health_loss_per_processed_unit=0,
            failure_probability=0 if stage.id in {"cnc_01", "quality_01"} else 1e-12,
            scrap_probability=0,
        ) for stage in line.stages))
        sim = ProductionLineSimulation(line, seed=123)
        for condition in sim.equipment.conditions.values():
            condition.burden = condition.wear = 0
        return sim

    def state(self, sim: ProductionLineSimulation) -> Any:
        return copy.deepcopy((sim.summary(), sim.event_log, sim._events,
                              sim.equipment.__dict__ | {"sim": None},
                              {k: v.getstate() for k, v in sim.rng._streams.items()}))

    def test_replay_all_actions_state_costs_timeline_and_digest(self) -> None:
        results = []
        for _ in range(2):
            manager = SessionManager()
            sid = manager.create_session(seed=9, scenario_mode="seeded")["session_id"]
            sim = manager._sessions[sid].simulation
            manager.pause_session(sid)
            manager.living_action(sid, "overtime")
            manager.living_action(sid, "containment")
            manager.place_purchase_order(sid, "STEEL-01", 250)
            manager.living_action(sid, "expedite", "PO-000001")
            manager.start_preventive_maintenance(sid, "cnc_01")
            manager.resume_session(sid)
            for minute in range(20, 541, 20):
                sim.advance_to(minute)
                for mid, spec in SPECS.items():
                    if spec.action and sim.equipment.unavailable(mid) is None:
                        manager.equipment_action(sid, mid, spec.action)
            snapshot = manager.get_session(sid)
            snapshot.pop("session_id")
            results.append((snapshot, sim.event_log, sim._events))
        self.assertEqual(*results)
        costs = results[0][0]["cost_breakdown"]
        for key in ("lens_gas_cleaning", "chemical_filter_service", "support_labor", "tester_calibration"):
            self.assertGreater(costs[key], 0)
        self.assertEqual(costs["total"], sum(v for k, v in costs.items() if k != "total"))

    def test_seed_variation_dominant_assets_and_fixed_topology(self) -> None:
        manager = SessionManager()
        topology = None
        dominant, digests = set(), set()
        normal_cnc = False
        for seed in range(32):
            snapshot = manager.create_session(seed=seed, scenario_mode="seeded")
            sim = manager._sessions[snapshot["session_id"]].simulation
            layout = [(mid, m.input_buffer, m.output_buffer) for mid, m in sim.machines.items()]
            capacities = [(bid, b.capacity) for bid, b in sim.buffers.items()]
            if topology is None:
                topology = layout, capacities
            self.assertEqual(topology, (layout, capacities))
            sim.advance_to(480)
            metrics = sim.summary()["machine_metrics"]
            loss = {mid: v["run_minutes"] - sim.machines[mid].config.ideal_cycle_minutes * v["processed"] + v["down_minutes"] for mid, v in metrics.items()}
            focus = max(loss, key=loss.get)
            dominant.add(focus)
            normal_cnc |= metrics["cnc_01"]["failures"] == 0 and focus != "cnc_01"
            digests.add(sim.digest())
        self.assertEqual(len(digests), 32)
        self.assertGreaterEqual(len(dominant), 5)
        self.assertTrue(normal_cnc)

    def test_service_decision_card_quotes_actual_cost_and_logs_choice(self) -> None:
        manager = SessionManager()
        sid = manager.create_session(seed=0, scenario_mode="seeded")["session_id"]
        result = manager.equipment_action(sid, "laser_01", "clean-lens")
        card = next(c for c in result["scenario_profile"]["decision_cards"] if c["id"] == "protect-asset")
        self.assertTrue(card["decision_logged"])
        self.assertIn("85 cost", card["detail"])
        self.assertIn("8 minutes", card["detail"])
        self.assertTrue(any("production stopped for 8 minutes" in row["title"] for row in result["timeline"]))
        result = manager.advance_session(sid, 8)
        self.assertTrue(any("normal cycles resume" in row["title"] for row in result["timeline"]))

    def test_equipment_service_incremental_advance_matches_whole_advance(self) -> None:
        a, b = self.controlled(), self.controlled()
        for sim in (a, b):
            sim.equipment.conditions["laser_01"].burden = 85
            sim.advance_to(.1)
            sim.equipment.request("laser_01", "clean-lens")
        for minute in range(1, 101):
            a.advance_to(minute)
        b.advance_to(100)
        self.assertEqual(self.state(a), self.state(b))
        self.assertEqual(a.digest(), b.digest())

    def test_each_condition_changes_actual_work_or_quality(self) -> None:
        for mid in SPECS:
            with self.subTest(asset=mid):
                good, bad = self.controlled(), self.controlled()
                bad.equipment.conditions[mid].burden = 100
                good.advance_to(300)
                bad.advance_to(300)
                a, b = good.summary(), bad.summary()
                self.assertGreater(b["machine_metrics"][mid]["cycle_time_multiplier"], a["machine_metrics"][mid]["cycle_time_multiplier"])
                if mid == "laser_01":
                    self.assertGreater(b["equipment_quality"]["source_rejects"], 0)
                    self.assertLess(b["good_production"], a["good_production"])
                elif mid == "wash_01":
                    self.assertGreater(b["equipment_quality"]["downstream_catches"], 0)
                elif mid in {"assembly_01", "test_01"}:
                    self.assertGreater(b["machine_metrics"][mid]["rework"], 0)
                    self.assertLess(b["good_production"], a["good_production"])
                else:
                    self.assertLess(b["machine_metrics"][mid]["performance"], a["machine_metrics"][mid]["performance"])

    def test_drift_and_overload_change_real_escapes(self) -> None:
        outcomes = []
        for bad in (False, True):
            sim = self.controlled()
            sim.equipment.defects.update({uid: "wash_01" for uid in range(1, 301)})
            if bad:
                sim.equipment.conditions["test_01"].burden = 100
                sim.equipment.conditions["quality_01"].burden = 100
            sim.advance_to(480)
            outcomes.append(sim.equipment.quality_summary())
        self.assertGreater(outcomes[1]["customer_escapes"], outcomes[0]["customer_escapes"])

    def test_services_restore_condition_consume_time_and_resolve_events(self) -> None:
        for mid, spec in SPECS.items():
            if not spec.action:
                continue
            with self.subTest(asset=mid):
                sim = self.controlled()
                sim.living = LivingShift(sim, "raw")
                sim.equipment.conditions[mid].burden = 85
                sim.equipment.reconcile()
                sim.equipment.request(mid, spec.action)
                sim.advance_to(spec.duration / 2)
                self.assertEqual(sim.machines[mid].processed_units, 0)
                self.assertAlmostEqual(sim.summary()["machine_metrics"][mid]["planned_maintenance_minutes"], spec.duration / 2)
                sim.advance_to(spec.duration)
                self.assertEqual(sim.equipment.conditions[mid].burden, 5)
                self.assertEqual(sim.equipment.conditions[mid].costs, spec.cost)
                self.assertEqual(sim.machines[mid].maintenance_count, 1)
                self.assertTrue(any(e.state == "resolved" and e.zone == mid for e in sim.living.events.values()))
                self.assertEqual(sim.equipment.metric(mid)["action_history"][0]["completed_minute"], spec.duration)
                before = self.state(sim)
                with self.assertRaises(ShiftActionUnavailableError):
                    sim.equipment.request(mid, spec.action)
                self.assertEqual(before, self.state(sim))

    def test_running_service_finishes_unit_then_stops_and_duplicates_are_atomic(self) -> None:
        sim = self.controlled()
        sim.equipment.conditions["laser_01"].burden = 80
        sim.advance_to(.1)
        unit = sim.machines["laser_01"].busy_unit
        sim.equipment.request("LASER-01", "clean-lens")
        self.assertTrue(sim.equipment.conditions["laser_01"].pending)
        self.assertEqual(sim.machines["laser_01"].busy_unit, unit)
        before = self.state(sim)
        for action in (lambda: sim.equipment.request("laser_01", "clean-lens"), lambda: sim.start_preventive_maintenance("laser_01")):
            with self.assertRaises(ShiftActionUnavailableError):
                action()
            self.assertEqual(before, self.state(sim))
        sim.advance_to(15)
        history = sim.equipment.conditions["laser_01"].history[0]
        self.assertGreater(history["started_minute"], .1)
        self.assertAlmostEqual(history["completed_minute"] - history["started_minute"], 8)
        outcomes = [e for e in sim.event_log if e.machine_id == "laser_01" and e.unit_id == unit and e.kind in {"PROCESS_COMPLETED", "UNIT_SCRAPPED"}]
        self.assertEqual(len(outcomes), 1)

    def test_wash_service_preserves_existing_defects(self) -> None:
        sim = self.controlled()
        sim.equipment.conditions["wash_01"].burden = 90
        sim.equipment.defects[999] = "wash_01"
        sim.equipment.request("wash_01", "service-wash")
        sim.advance_to(12)
        self.assertEqual(sim.equipment.defects[999], "wash_01")
        self.assertEqual(sim.equipment.risk("wash_01"), 0)

    def test_containment_catches_wash_defects_without_double_counting(self) -> None:
        sim = self.controlled()
        sim.living = LivingShift(sim, "raw")
        sim.living.containment_available = True
        sim.living.activate_containment()
        for mid in ("wash_01", "test_01", "quality_01"):
            sim.equipment.conditions[mid].burden = 100
        sim.advance_to(480)
        quality = sim.equipment.quality_summary()
        self.assertGreater(sim.living.captured_units, 0)
        self.assertEqual(quality["customer_escapes"], 0)
        self.assertEqual(quality["suspect_finished_goods"], 0)
        self.assertEqual(sim.living.captured_units, sum(e.kind == "LATENT_DEFECT_CONTAINED" for e in sim.event_log))

    def test_support_resolves_v3_operator_shortage(self) -> None:
        sim = self.controlled()
        sim.living = LivingShift(sim, "assembly_01")
        event = next(e for e in sim.living.events.values() if e.kind == "operator_shortage")
        sim.advance_to(event.minute)
        sim.equipment.conditions["assembly_01"].burden = 80
        sim.equipment.request("assembly_01", "assign-support")
        sim.advance_to(event.minute + 15)
        self.assertEqual(event.state, "resolved")

    def test_unit_conservation_with_rework_scrap_and_service(self) -> None:
        sim = self.controlled()
        for c in sim.equipment.conditions.values():
            c.burden = 90
        sim.advance_to(30)
        sim.equipment.request("assembly_01", "assign-support")
        sim.advance_to(480)
        physical = sum(b.size for b in sim.buffers.values()) + sum(m.busy_unit is not None for m in sim.machines.values())
        scrap = sum(m.scrap_units for m in sim.machines.values())
        self.assertEqual(physical + scrap, 300)
        self.assertEqual(sim.summary()["total_scrap"], scrap)
        finished = [e.unit_id for e in sim.event_log if e.kind == "FINISHED_GOODS_RECEIVED"]
        self.assertEqual(len(finished), len(set(finished)))


class EquipmentApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)

    def test_all_endpoints_validation_duplicate_cost_and_control_hold(self) -> None:
        for mid, spec in SPECS.items():
            if not spec.action:
                continue
            sid = self.client.post("/sessions", json={"seed": 0, "scenario_mode": "seeded"}).json()["session_id"]
            session_manager._sessions[sid].simulation.equipment.conditions[mid].burden = 80
            path = f"/sessions/{sid}"
            self.client.post(path + "/pause")
            url = path + "/actions/" + spec.action
            for body, status in (({}, 422), ({"machine_id": 4}, 422), ({"machine_id": mid, "cost": 0}, 422), ({"machine_id": "missing"}, 404), ({"machine_id": "cnc_01"}, 409)):
                before = self.client.get(path).json()
                response = self.client.post(url, json=body)
                self.assertEqual(response.status_code, status, response.text)
                self.assertEqual(self.client.get(path).json(), before)
            response = self.client.post(url, json={"machine_id": mid})
            self.assertEqual(response.status_code, 200, response.text)
            accepted = response.json()
            self.assertTrue(accepted["paused"])
            self.assertEqual(accepted["cost_breakdown"][spec.cost_category], spec.cost)
            self.assertEqual(self.client.post(url, json={"machine_id": mid}).status_code, 409)
            self.assertEqual(accepted, self.client.get(path).json())
            self.assertEqual(self.client.post(path + "/advance", json={"minutes": 1}).status_code, 409)
            self.assertEqual(self.client.post(f"/sessions/missing/actions/{spec.action}", json={"machine_id": mid}).status_code, 404)
            self.client.post(path + "/resume")
            finished = self.client.post(path + "/advance", json={"minutes": spec.duration}).json()
            self.assertEqual(finished["summary"]["machine_metrics"][mid]["condition_value"], 5)

    def test_closed_and_classic_rejections_are_atomic(self) -> None:
        for mode in ("classic", "seeded"):
            sid = self.client.post("/sessions", json={"scenario_mode": mode}).json()["session_id"]
            path = f"/sessions/{sid}"
            if mode == "seeded":
                self.client.post(path + "/advance", json={"minutes": 480})
            before = self.client.get(path).json()
            response = self.client.post(path + "/actions/service-wash", json={"machine_id": "wash_01"})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(before, self.client.get(path).json())
