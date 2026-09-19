import type { SessionSnapshot, Workspace } from "../types";
import type { Message } from "../i18n/core";

export interface DecisionFeedback {
  title: Message;
  minute: number;
  workspace: Workspace;
  changes: { label: string; id?: string; before: string | number; after: string | number }[];
  expected: string[];
}
// Read-only comparison of the snapshots surrounding a confirmed command response.
export function decisionFeedback(before: SessionSnapshot, after: SessionSnapshot, title: Message): DecisionFeedback | null {
  if (before.session_id !== after.session_id) return null;
  const result: DecisionFeedback = { title, minute: after.summary.simulated_minutes, workspace: "Reports", changes: [], expected: [] };
  const add = (label: string, a: string | number, b: string | number, id?: string) => {
    if (a !== b) result.changes.push({ label, before: a, after: b, id });
  };
  add("Total committed cost", before.cost_breakdown.total, after.cost_breakdown.total);
  add("Inbound material", before.summary.supply_summary.inbound_units, after.summary.supply_summary.inbound_units);
  add("Overtime minutes authorized", before.overtime?.authorized ? before.overtime.extension_minutes : 0, after.overtime?.authorized ? after.overtime.extension_minutes : 0);
  add("Quality containment", before.quality_containment?.active ? "Active" : "Inactive", after.quality_containment?.active ? "Active" : "Inactive");
  add("Customer commitment value", before.decision_review?.customer_value ?? 0, after.decision_review?.customer_value ?? 0);
  for (const [id, m] of Object.entries(after.summary.machine_metrics)) {
    const old = before.summary.machine_metrics[id]; if (!old) continue;
    add("Machine state", old.state, m.state, id); add("Health", old.health, m.health, id);
    add("Cycle time multiplier", old.cycle_time_multiplier ?? 1, m.cycle_time_multiplier ?? 1, id);
    if (m.service?.pending && !old.service?.pending) add("Service queued", "Inactive", "Active", id);
    if ((m.service?.pending && !old.service?.pending) || (m.state === "PLANNED_MAINTENANCE" && old.state !== m.state)) {
      result.expected.push("Service restores health after completion; the stop may expose delivery. Existing suspect WIP remains.");
      result.workspace = "Maintenance";
    }
  }
  for (const order of after.summary.order_summary.orders) {
    const old = before.summary.order_summary.orders.find(o => o.id === order.id);
    if (old) add("Order priority", old.priority, order.priority, order.id);
  }
  for (const po of after.summary.supply_summary.purchase_orders) {
    const old = before.summary.supply_summary.purchase_orders.find(p => p.id === po.id);
    if (old) add("Expected receipt minute", old.expected_receipt_minute ?? old.promised_receipt_minute, po.expected_receipt_minute ?? po.promised_receipt_minute, po.id);
  }
  for (const event of after.shift_events ?? []) {
    const old = before.shift_events?.find(e => e.id === event.id);
    if (!old || !event.selected_choice || old.selected_choice === event.selected_choice) continue;
    result.workspace = event.workspace;
    add("Selected response", "No intervention selected", event.choices?.find(c => c.id === event.selected_choice)?.label ?? "Existing service", event.id);
    if (event.expected) result.expected.push(event.expected);
    add("Operational pressure", old.pressure ?? 1, event.pressure ?? 1, event.id);
    add("Pressure end minute", old.effect_until ?? old.end_minute, event.effect_until ?? event.end_minute, event.id);
  }
  return result.changes.length ? result : null;
}
