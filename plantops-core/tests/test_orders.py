from __future__ import annotations

import unittest

from plantops_sim import ProductionLineSimulation, make_mvp_scenario
from plantops_sim.model import OrderConfig, Scenario, StageConfig, UrgentOrderRule


def make_controlled_order_scenario(
    *,
    raw_material_units: int,
    orders: tuple[OrderConfig, ...],
    cycle_minutes: float = 0.1,
    cnc_failure_probability: float = 0,
    repair_minutes: float = 0,
    urgent_order_rule: UrgentOrderRule | None = None,
) -> Scenario:
    stages = tuple(
        StageConfig(
            id=stage_id,
            name=stage_id,
            ideal_cycle_minutes=cycle_minutes,
            cycle_jitter=0,
            failure_probability=(
                cnc_failure_probability if stage_id == "cnc_01" else 0
            ),
            repair_min_minutes=repair_minutes if stage_id == "cnc_01" else 0,
            repair_max_minutes=repair_minutes if stage_id == "cnc_01" else 0,
        )
        for stage_id in ("cnc_01", "wash_01", "assembly_01", "quality_01")
    )
    return Scenario(
        raw_material_units=raw_material_units,
        shift_minutes=10,
        stages=stages,
        buffer_capacities={
            "raw": raw_material_units,
            "after_cnc_01": 10,
            "after_wash_01": 10,
            "after_assembly_01": 10,
            "finished": None,
        },
        orders=orders,
        urgent_order_rule=urgent_order_rule,
    )


def order_by_id(summary, order_id: str):
    return next(order for order in summary["orders"] if order["id"] == order_id)


class OrderSimulationTests(unittest.TestCase):
    def test_same_seed_reproduces_urgent_order_summary_and_digest(self):
        first = ProductionLineSimulation(make_mvp_scenario(), seed=77)
        second = ProductionLineSimulation(make_mvp_scenario(), seed=77)

        first_summary = first.run(480)
        second_summary = second.run(480)
        first_urgent = order_by_id(first_summary["order_summary"], "ORDER-URGENT")
        second_urgent = order_by_id(second_summary["order_summary"], "ORDER-URGENT")

        self.assertEqual(first_urgent, second_urgent)
        self.assertEqual(first_summary, second_summary)
        self.assertEqual(first.digest(), second.digest())
        self.assertEqual(first_summary["event_counts"]["URGENT_ORDER_RECEIVED"], 1)

    def test_different_seed_can_change_urgent_order(self):
        first = ProductionLineSimulation(make_mvp_scenario(), seed=11)
        second = ProductionLineSimulation(make_mvp_scenario(), seed=12)

        first_urgent = order_by_id(first.summary()["order_summary"], "ORDER-URGENT")
        second_urgent = order_by_id(second.summary()["order_summary"], "ORDER-URGENT")

        self.assertNotEqual(first_urgent, second_urgent)

    def test_earlier_due_order_receives_good_units_first(self):
        scenario = make_controlled_order_scenario(
            raw_material_units=1,
            orders=(
                OrderConfig("LATER", 1, 0, 6, 10),
                OrderConfig("EARLIER", 1, 0, 5, 1),
            ),
        )
        simulation = ProductionLineSimulation(scenario, seed=1)

        order_summary = simulation.advance_to(1)["order_summary"]

        self.assertEqual(order_by_id(order_summary, "EARLIER")["fulfilled_quantity"], 1)
        self.assertEqual(order_by_id(order_summary, "LATER")["fulfilled_quantity"], 0)

    def test_higher_priority_breaks_equal_due_time_tie(self):
        scenario = make_controlled_order_scenario(
            raw_material_units=1,
            orders=(
                OrderConfig("LOW", 1, 0, 5, 1),
                OrderConfig("HIGH", 1, 0, 5, 10),
            ),
        )
        simulation = ProductionLineSimulation(scenario, seed=1)

        order_summary = simulation.advance_to(1)["order_summary"]

        self.assertEqual(order_by_id(order_summary, "HIGH")["fulfilled_quantity"], 1)
        self.assertEqual(order_by_id(order_summary, "LOW")["fulfilled_quantity"], 0)

    def test_order_id_is_final_allocation_tiebreaker(self):
        scenario = make_controlled_order_scenario(
            raw_material_units=1,
            orders=(
                OrderConfig("ORDER-B", 1, 0, 5, 1),
                OrderConfig("ORDER-A", 1, 0, 5, 1),
            ),
        )
        simulation = ProductionLineSimulation(scenario, seed=1)

        order_summary = simulation.advance_to(1)["order_summary"]

        self.assertEqual(order_by_id(order_summary, "ORDER-A")["fulfilled_quantity"], 1)
        self.assertEqual(order_by_id(order_summary, "ORDER-B")["fulfilled_quantity"], 0)

    def test_incomplete_order_emits_order_late_exactly_once(self):
        scenario = make_controlled_order_scenario(
            raw_material_units=0,
            orders=(OrderConfig("MISSED", 2, 0, 1, 1),),
        )
        simulation = ProductionLineSimulation(scenario, seed=1)

        simulation.advance_to(2)
        simulation.advance_to(5)

        summary = simulation.summary()
        self.assertEqual(summary["event_counts"]["ORDER_DUE"], 1)
        self.assertEqual(summary["event_counts"]["ORDER_LATE"], 1)
        self.assertEqual(summary["order_summary"]["orders_late"], 1)
        self.assertEqual(
            order_by_id(summary["order_summary"], "MISSED")["status"],
            "LATE",
        )

    def test_otif_is_null_before_any_order_is_due(self):
        scenario = make_controlled_order_scenario(
            raw_material_units=0,
            orders=(OrderConfig("FUTURE", 1, 0, 5, 1),),
        )

        summary = ProductionLineSimulation(scenario, seed=1).summary()

        self.assertIsNone(summary["order_summary"]["otif"])

    def test_otif_is_one_when_due_order_was_fully_on_time(self):
        scenario = make_controlled_order_scenario(
            raw_material_units=1,
            orders=(OrderConfig("ON-TIME", 1, 0, 1, 1),),
            cycle_minutes=0.25,
        )

        summary = ProductionLineSimulation(scenario, seed=1).advance_to(1)

        self.assertEqual(summary["order_summary"]["otif"], 1.0)
        self.assertEqual(summary["order_summary"]["units_on_time"], 1)

    def test_missed_due_order_lowers_otif(self):
        scenario = make_controlled_order_scenario(
            raw_material_units=1,
            orders=(
                OrderConfig("FIRST", 1, 0, 1, 1),
                OrderConfig("SECOND", 1, 0, 1, 1),
            ),
        )

        summary = ProductionLineSimulation(scenario, seed=1).advance_to(1)

        self.assertEqual(summary["order_summary"]["orders_due"], 2)
        self.assertEqual(summary["order_summary"]["otif"], 0.5)

    def test_expedited_repair_can_change_delivery_outcome(self):
        scenario = make_controlled_order_scenario(
            raw_material_units=2,
            orders=(OrderConfig("CUSTOMER", 2, 0, 3, 1),),
            cycle_minutes=0.5,
            cnc_failure_probability=1.0,
            repair_minutes=10,
        )
        ordinary = ProductionLineSimulation(scenario, seed=1)
        expedited = ProductionLineSimulation(scenario, seed=1)
        ordinary.advance_to(0.6)
        expedited.advance_to(0.6)

        expedited.expedite_repair("CNC-01")
        ordinary_summary = ordinary.advance_to(3)["order_summary"]
        expedited_summary = expedited.advance_to(3)["order_summary"]

        self.assertEqual(ordinary_summary["otif"], 0.0)
        self.assertEqual(expedited_summary["otif"], 1.0)

    def test_good_unit_waits_in_stock_before_order_release(self):
        scenario = make_controlled_order_scenario(
            raw_material_units=1,
            orders=(OrderConfig("FUTURE", 1, 2, 5, 1),),
        )
        simulation = ProductionLineSimulation(scenario, seed=1)

        summary = simulation.advance_to(1)

        self.assertEqual(summary["good_production"], 1)
        self.assertEqual(summary["finished_goods_available"], 1)
        self.assertEqual(summary["finished_goods_allocated"], 0)
        self.assertEqual(summary["order_summary"]["units_delivered"], 0)
        self.assertEqual(summary["event_counts"]["FINISHED_GOODS_RECEIVED"], 1)

    def test_order_release_consumes_existing_stock_immediately_in_fifo_order(self):
        scenario = make_controlled_order_scenario(
            raw_material_units=2,
            orders=(OrderConfig("FUTURE", 2, 2, 5, 1),),
        )
        simulation = ProductionLineSimulation(scenario, seed=1)
        simulation.advance_to(1)

        summary = simulation.advance_to(2)

        order = order_by_id(summary["order_summary"], "FUTURE")
        self.assertEqual(order["fulfilled_quantity"], 2)
        self.assertEqual(summary["finished_goods_available"], 0)
        self.assertEqual(summary["finished_goods_allocated"], 2)
        allocation_events = [
            event for event in simulation.event_log if event.kind == "ORDER_UNIT_ALLOCATED"
        ]
        self.assertEqual([event.unit_id for event in allocation_events], [1, 2])
        self.assertTrue(
            all(event.detail == "order_id=FUTURE" for event in allocation_events)
        )

    def test_seeded_urgent_order_consumes_preexisting_stock(self):
        urgent_rule = UrgentOrderRule(
            id="URGENT",
            min_arrival_minute=2,
            max_arrival_minute=2,
            min_quantity=1,
            max_quantity=1,
            lead_time_minutes=2,
            priority=10,
        )
        scenario = make_controlled_order_scenario(
            raw_material_units=1,
            orders=(),
            urgent_order_rule=urgent_rule,
        )
        simulation = ProductionLineSimulation(scenario, seed=1)
        before_release = simulation.advance_to(1)

        after_release = simulation.advance_to(2)

        self.assertEqual(before_release["finished_goods_available"], 1)
        self.assertEqual(after_release["finished_goods_available"], 0)
        self.assertEqual(after_release["finished_goods_allocated"], 1)
        self.assertEqual(after_release["order_summary"]["units_delivered"], 1)
        self.assertEqual(after_release["event_counts"]["URGENT_ORDER_RECEIVED"], 1)

    def test_stock_allocated_after_deadline_counts_as_late(self):
        scenario = make_controlled_order_scenario(
            raw_material_units=1,
            orders=(OrderConfig("LATE-RELEASE", 1, 2, 1, 1),),
        )
        simulation = ProductionLineSimulation(scenario, seed=1)
        manufactured = simulation.advance_to(1)

        allocated = simulation.advance_to(2)

        self.assertEqual(manufactured["finished_goods_available"], 1)
        order = order_by_id(allocated["order_summary"], "LATE-RELEASE")
        self.assertEqual(order["status"], "COMPLETED_LATE")
        self.assertEqual(allocated["order_summary"]["units_on_time"], 0)
        self.assertEqual(allocated["order_summary"]["units_late"], 1)

    def test_finished_goods_and_backlog_accounting_invariants(self):
        simulation = ProductionLineSimulation(make_mvp_scenario(), seed=42)

        initial = simulation.summary()
        final = simulation.run(480)

        self.assertEqual(initial["order_summary"]["backlog_orders"], 3)
        self.assertEqual(initial["order_summary"]["backlog_units"], 260)
        for summary in (initial, final):
            self.assertEqual(
                summary["finished_goods_total"],
                summary["finished_goods_available"]
                + summary["finished_goods_allocated"],
            )
            self.assertEqual(summary["finished_goods_total"], summary["good_production"])
            self.assertEqual(
                summary["finished_goods_allocated"],
                summary["order_summary"]["units_delivered"],
            )


if __name__ == "__main__":
    unittest.main()
