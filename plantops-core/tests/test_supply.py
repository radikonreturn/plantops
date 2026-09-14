from __future__ import annotations

import unittest

from plantops_sim import ProductionLineSimulation, make_mvp_scenario
from plantops_sim.engine import (
    InvalidPurchaseQuantityError,
    UnknownSupplierError,
)
from plantops_sim.model import (
    PurchaseOrderStatus,
    Scenario,
    StageConfig,
    SupplierConfig,
)


def make_supplier(
    *,
    min_lead_minutes: float = 2,
    max_lead_minutes: float = 2,
    late_probability: float = 0,
    max_delay_minutes: float = 4,
) -> SupplierConfig:
    return SupplierConfig(
        id="SUPPLIER-01",
        name="Controlled Steel Supplier",
        min_lead_minutes=min_lead_minutes,
        max_lead_minutes=max_lead_minutes,
        late_probability=late_probability,
        max_delay_minutes=max_delay_minutes,
        unit_cost=12.5,
    )


def make_supply_scenario(
    *,
    raw_material_units: int,
    supplier: SupplierConfig,
    cycle_minutes: float = 1,
) -> Scenario:
    stages = tuple(
        StageConfig(
            id=stage_id,
            name=stage_id,
            ideal_cycle_minutes=cycle_minutes,
            cycle_jitter=0,
        )
        for stage_id in ("cnc_01", "wash_01", "assembly_01", "quality_01")
    )
    return Scenario(
        raw_material_units=raw_material_units,
        shift_minutes=1_200,
        stages=stages,
        buffer_capacities={
            "raw": None,
            "after_cnc_01": 10,
            "after_wash_01": 10,
            "after_assembly_01": 10,
            "finished": None,
        },
        suppliers=(supplier,),
    )


class SupplySimulationTests(unittest.TestCase):
    def test_mvp_starts_below_planned_demand_with_one_supplier(self):
        scenario = make_mvp_scenario()
        minimum_planned_demand = (
            sum(order.quantity for order in scenario.orders)
            + scenario.urgent_order_rule.min_quantity
        )

        self.assertEqual(scenario.raw_material_units, 200)
        self.assertLess(scenario.raw_material_units, minimum_planned_demand)
        self.assertEqual([supplier.id for supplier in scenario.suppliers], ["STEEL-01"])

    def test_purchase_order_does_not_immediately_change_raw_stock(self):
        simulation = ProductionLineSimulation(
            make_supply_scenario(
                raw_material_units=2,
                supplier=make_supplier(),
            ),
            seed=42,
        )
        raw_before = list(simulation.buffers["raw"].units)

        purchase_order = simulation.place_purchase_order("SUPPLIER-01", 3)
        summary = simulation.summary()

        self.assertEqual(simulation.buffers["raw"].units, raw_before)
        self.assertEqual(purchase_order.status, PurchaseOrderStatus.OPEN)
        self.assertIsNone(purchase_order.actual_receipt_minute)
        self.assertEqual(summary["supply_summary"]["inbound_units"], 3)
        self.assertEqual(summary["supply_summary"]["received_units"], 0)
        self.assertEqual(summary["supply_summary"]["procurement_committed_cost"], 37.5)
        placed_event = simulation.event_log[-1]
        self.assertEqual(placed_event.kind, "PURCHASE_ORDER_PLACED")
        self.assertNotIn("actual_receipt_minute", placed_event.detail)
        self.assertNotIn("late", placed_event.detail.casefold())

    def test_receipt_adds_exact_quantity_with_unique_new_unit_ids(self):
        simulation = ProductionLineSimulation(
            make_supply_scenario(
                raw_material_units=2,
                supplier=make_supplier(min_lead_minutes=1, max_lead_minutes=1),
                cycle_minutes=100,
            ),
            seed=42,
        )
        purchase_order = simulation.place_purchase_order("SUPPLIER-01", 3)

        summary = simulation.advance_to(1)

        represented_raw_ids = {
            *simulation.buffers["raw"].units,
            simulation.machines["cnc_01"].busy_unit,
        }
        self.assertEqual(represented_raw_ids, {1, 2, 3, 4, 5})
        self.assertEqual(simulation.buffers["raw"].units[-3:], [3, 4, 5])
        self.assertEqual(summary["supply_summary"]["received_units"], 3)
        self.assertEqual(summary["event_counts"]["MATERIAL_RECEIVED"], 1)
        self.assertEqual(purchase_order.status, PurchaseOrderStatus.RECEIVED_ON_TIME)

    def test_receipt_restarts_a_starved_cnc(self):
        simulation = ProductionLineSimulation(
            make_supply_scenario(
                raw_material_units=0,
                supplier=make_supplier(),
            ),
            seed=42,
        )
        simulation.advance_to(0)
        self.assertEqual(simulation.machines["cnc_01"].state.value, "STARVED")

        simulation.place_purchase_order("SUPPLIER-01", 2)
        before_receipt = simulation.advance_to(1)
        after_receipt = simulation.advance_to(2)

        self.assertEqual(before_receipt["supply_summary"]["raw_material_on_hand"], 0)
        self.assertEqual(simulation.machines["cnc_01"].state.value, "RUNNING")
        self.assertEqual(simulation.machines["cnc_01"].busy_unit, 1)
        self.assertEqual(after_receipt["supply_summary"]["raw_material_on_hand"], 1)
        self.assertEqual(after_receipt["supply_summary"]["received_units"], 2)

    def test_same_seed_and_action_sequence_reproduces_supply_outcome(self):
        scenario = make_supply_scenario(
            raw_material_units=1,
            supplier=make_supplier(
                min_lead_minutes=3,
                max_lead_minutes=8,
                late_probability=0.5,
                max_delay_minutes=5,
            ),
        )
        first = ProductionLineSimulation(scenario, seed=91)
        second = ProductionLineSimulation(scenario, seed=91)

        for simulation in (first, second):
            simulation.place_purchase_order("SUPPLIER-01", 4)
            simulation.advance_to(1)
            simulation.place_purchase_order("SUPPLIER-01", 6)
            simulation.advance_to(30)

        self.assertEqual(first.summary(), second.summary())
        self.assertEqual(first.digest(), second.digest())
        self.assertEqual(
            first.summary()["supply_summary"]["purchase_orders"],
            second.summary()["supply_summary"]["purchase_orders"],
        )

    def test_pending_purchase_does_not_shift_production_random_streams(self):
        scenario = make_mvp_scenario(raw_material_units=20)
        baseline = ProductionLineSimulation(scenario, seed=77)
        purchasing = ProductionLineSimulation(scenario, seed=77)

        purchasing.place_purchase_order("STEEL-01", 10)
        baseline.advance_to(30)
        purchasing.advance_to(30)

        production_events_with_purchase = [
            event
            for event in purchasing.event_log
            if event.kind != "PURCHASE_ORDER_PLACED"
        ]
        self.assertEqual(production_events_with_purchase, baseline.event_log)
        self.assertEqual(
            purchasing.summary()["machine_metrics"],
            baseline.summary()["machine_metrics"],
        )
        self.assertEqual(
            purchasing.summary()["order_summary"],
            baseline.summary()["order_summary"],
        )

    def test_forced_late_delivery_emits_one_late_event(self):
        simulation = ProductionLineSimulation(
            make_supply_scenario(
                raw_material_units=0,
                supplier=make_supplier(late_probability=1),
            ),
            seed=12,
        )
        purchase_order = simulation.place_purchase_order("SUPPLIER-01", 2)

        simulation.advance_to(20)
        simulation.advance_to(30)

        self.assertEqual(purchase_order.status, PurchaseOrderStatus.RECEIVED_LATE)
        self.assertIsNotNone(purchase_order.actual_receipt_minute)
        self.assertGreater(
            purchase_order.actual_receipt_minute,
            purchase_order.promised_receipt_minute,
        )
        late_events = [
            event
            for event in simulation.event_log
            if event.kind == "PURCHASE_ORDER_LATE"
        ]
        self.assertEqual(len(late_events), 1)
        self.assertEqual(simulation.summary()["supply_summary"]["purchase_orders_late"], 1)

    def test_invalid_supplier_and_quantity_do_not_mutate_state(self):
        simulation = ProductionLineSimulation(
            make_supply_scenario(
                raw_material_units=2,
                supplier=make_supplier(),
            ),
            seed=42,
        )
        summary_before = simulation.summary()
        digest_before = simulation.digest()

        with self.assertRaises(UnknownSupplierError):
            simulation.place_purchase_order("UNKNOWN", 1)
        for quantity in (0, -1, 1_001, True, 1.5):
            with self.subTest(quantity=quantity):
                with self.assertRaises(InvalidPurchaseQuantityError):
                    simulation.place_purchase_order("SUPPLIER-01", quantity)

        self.assertEqual(simulation.summary(), summary_before)
        self.assertEqual(simulation.digest(), digest_before)

    def test_supplier_config_validates_all_fields(self):
        valid = {
            "id": "SUPPLIER-01",
            "name": "Supplier",
            "min_lead_minutes": 1,
            "max_lead_minutes": 2,
            "late_probability": 0.2,
            "max_delay_minutes": 3,
            "unit_cost": 1.5,
        }
        invalid_values = {
            "id": "",
            "name": " ",
            "min_lead_minutes": 0,
            "max_lead_minutes": 0.5,
            "late_probability": 1.1,
            "max_delay_minutes": 0,
            "unit_cost": -0.1,
        }

        for field, value in invalid_values.items():
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    SupplierConfig(**(valid | {field: value}))


if __name__ == "__main__":
    unittest.main()
