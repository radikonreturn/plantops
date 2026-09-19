import type { SessionSnapshot, ShiftEvent } from "../types";
import { en, type TranslationKey } from "./en";
import { knownText, translate, type Locale, type Values } from "./core";

export function backendText(locale: Locale, id: string, original: string, values?: Values): string {
  if (locale === "en" || !Object.prototype.hasOwnProperty.call(en, id)) return original;
  return translate(locale, id as TranslationKey, values);
}

const equipment = {
  laser_01: { fault: "lens contamination / assist-gas instability", impact: "Slower cutting; contaminated optics increase source scrap." },
  cnc_01: { fault: "spindle wear warning", impact: "Spindle health falls by 18 points; wear increases breakdown exposure until serviced." },
  wash_01: { fault: "filter differential above control limit", impact: "Residue travels with parts; downstream inspection or containment must catch it." },
  assembly_01: { fault: "torque tool verification overdue", impact: "Reduced station capacity; torque verification adds rework time." },
  test_01: { fault: "calibration drift suspected", impact: "False failures add retests; drift reduces detection of residue defects." },
  quality_01: { fault: "inspection queue exceeds release capacity", impact: "Release capacity falls; overloaded sampling can miss upstream defects." },
} as const;
const eventMessages = {
  supplier_delay: ["Supplier transport disruption", "Open receipts and orders placed during this 60-minute disruption gain 25 minutes of transit time once."],
  customer_escalation: ["Customer dispatch escalation", "An unfinished released order gains 15 priority points (capped at 100); earliest due still governs allocation."],
  operator_shortage: ["Temporary operator shortage", "New cycles at this station take 40% longer for 60 minutes."],
  quality_notice: ["QUALITY-01: containment pressure", "Latent defect exposure rises from 6% to 12% of units passing normal inspection for 60 minutes."],
} as const;

export function localizeEvent(locale: Locale, event: ShiftEvent): ShiftEvent {
  if (locale === "en") return event;
  const spec = equipment[event.zone as keyof typeof equipment];
  if (spec && ["condition_risk", "equipment_condition"].includes(event.kind)) {
    return { ...event, title: `${event.zone.replace("_", "-").toUpperCase()}: ${knownText(locale, spec.fault)}`, detail: knownText(locale, spec.impact) };
  }
  const copy = eventMessages[event.kind as keyof typeof eventMessages];
  if (!copy) return event;
  return { ...event, title: event.kind === "operator_shortage" && event.zone === "assembly_01"
    ? `ASSEMBLY-01: ${knownText(locale, "staffing shortage")}` : knownText(locale, copy[0]), detail: knownText(locale, copy[1]) };
}

// Display-only projection. IDs, state codes, quantities, costs and the original
// engine snapshot are never changed. Unknown backend copy stays in English.
export function localizeSession(original: SessionSnapshot, locale: Locale): SessionSnapshot {
  if (locale === "en") return original;
  const session = structuredClone(original);
  const t = (key: TranslationKey, values?: Values) => translate(locale, key, values);
  const text = (value: string) => knownText(locale, value);
  const nullable = (value: string | null) => value === null ? null : text(value);
  const pct = (value: number, digits = 0) => new Intl.NumberFormat("tr-TR", { style: "percent", maximumFractionDigits: digits }).format(value);
  const p = session.scenario_profile, s = session.summary;
  p.title = backendText(locale, `profile.${p.id}.title`, p.title);
  p.briefing = backendText(locale, `profile.${p.id}.briefing`, p.briefing);
  p.capacity.estimate_note = text(p.capacity.estimate_note);
  for (const asset of p.machines) {
    const metric = s.machine_metrics[asset.id];
    asset.name = text(asset.name);
    asset.fault_mode = text(asset.fault_mode);
    asset.maintenance_label = text(asset.maintenance_label);
    asset.maintenance_unavailable_reason = nullable(asset.maintenance_unavailable_reason);
    if (metric.condition_label) metric.condition_label = text(metric.condition_label);
    if (metric.active_issue) metric.active_issue = text(metric.active_issue);
    if (metric.service) {
      metric.service.label = text(metric.service.label);
      metric.service.unavailable_reason = nullable(metric.service.unavailable_reason);
    }
    if (asset.attention_reason) {
      if (metric.service?.pending) asset.attention_reason = t("Service queued; current unit will finish first.");
      else if (metric.active_issue) asset.attention_reason = metric.active_issue;
      else if (asset.scrap_probability > .05) asset.attention_reason = t("Configured lot rejection {risk}; {scrap} observed scrap.", { risk: pct(asset.scrap_probability), scrap: metric.scrap });
      else if (metric.state === "DOWN") asset.attention_reason = t("{asset}: stopped for repair.", { asset: asset.fault_mode });
      else if (metric.health < 65 && asset.failure_risk > 0) asset.attention_reason = t("{fault}: health {health}/100.", { fault: asset.fault_mode, health: metric.health.toFixed(1) });
      else if (metric.state === "PLANNED_MAINTENANCE") asset.attention_reason = t("{service} in progress.", { service: asset.maintenance_label });
      else if (metric.state === "BLOCKED") asset.attention_reason = t("Output buffer {buffer} is full.", { buffer: asset.output_buffer });
      else if (metric.state === "STARVED") asset.attention_reason = t("Waiting for material in {buffer}.", { buffer: asset.input_buffer });
      else asset.attention_reason = text(asset.attention_reason);
    }
  }
  session.shift_events = session.shift_events?.map(event => localizeEvent(locale, event));
  for (const alert of p.active_alerts) {
    const event = session.shift_events?.find(e => e.id === alert.id);
    const asset = p.machines.find(m => m.id === alert.zone);
    const metric = asset ? s.machine_metrics[asset.id] : null;
    const zone = p.scene.zones.find(z => `queue-${z.id}` === alert.id);
    const order = s.order_summary.orders.find(o => `order-${o.id}` === alert.id);
    if (event) alert.message = `${event.title}: ${event.detail}`;
    else if (asset && metric && alert.id === `condition-${asset.id}`) alert.message = `${asset.id.replace("_", "-").toUpperCase()}: ${metric.active_issue}`;
    else if (asset && metric && alert.id === `down-${asset.id}`) alert.message = t("{asset} is DOWN ({fault}). Review emergency repair.", { asset: asset.name, fault: asset.fault_mode });
    else if (asset && metric && alert.id === `wear-${asset.id}`) alert.message = t("{asset}: {fault}; health {health}/100, {risk} risk per unit.", { asset: asset.name, fault: asset.fault_mode, health: metric.health.toFixed(1), risk: pct(asset.failure_risk, 1) });
    else if (zone) alert.message = t("{buffer}: {units}/{capacity} places occupied.", { buffer: zone.id, units: zone.units, capacity: zone.capacity });
    else if (order) alert.message = t("{order}: {risk} against its dispatch deadline.", { order: order.id, risk: text(p.scene.order_risks[order.id]) });
    else if (alert.id === "material-coverage") alert.message = t("{units} units of demand lack material coverage before scrap allowance.", { units: p.scene.receiving.uncovered_demand });
    else if (alert.id === "quality-risk") alert.message = t("Lot reject risk is {risk}; {scrap} units have actually been scrapped.", { risk: pct(p.machines.find(m => m.stage_role === "quality")?.scrap_probability ?? 0), scrap: s.scrap });
    else if (alert.id === "inbound") alert.message = t("{units} units inbound on {orders} open POs.", { units: s.supply_summary.inbound_units, orders: s.supply_summary.purchase_orders_open });
  }
  for (const id of Object.keys(p.scene.order_risks)) p.scene.order_risks[id] = text(p.scene.order_risks[id]);
  if (session.overtime) session.overtime.unavailable_reason = nullable(session.overtime.unavailable_reason);
  if (session.quality_containment) session.quality_containment.unavailable_reason = nullable(session.quality_containment.unavailable_reason);
  for (const card of p.decision_cards) {
    card.status = text(card.status);
    const asset = p.machines.find(m => m.id === p.primary_zone);
    if (card.id === "protect-asset" && asset) {
      const service = s.machine_metrics[asset.id].service;
      card.title = t("Decide on {asset}", { asset: asset.name });
      card.detail = `${asset.fault_mode}. ${asset.attention_reason ?? t("Review health, queue and delivery exposure before acting.")} ${service
        ? t("{service}: {duration} minutes stopped / {cost} cost / restores underlying condition after the current unit.", { service: service.label, duration: service.duration, cost: service.cost })
        : t("Service: {duration} minutes stopped / {cost} cost / restores health to 100.", { duration: asset.maintenance_duration, cost: asset.maintenance_cost })}`;
    } else if (card.id === "secure-material") {
      card.title = t("Secure material coverage");
      card.detail = t("The line has {units} units of available or inbound material. Purchasing commits quantity × unit cost. Expedite an open PO for 120 cost to halve its remaining transit time; later disruption can still delay it.", { units: s.supply_summary.inbound_units + s.supply_summary.raw_material_on_hand });
    } else if (card.id === "contain-quality") {
      card.title = t("Plan for quality containment");
      card.detail = t("Source rejection risk remains unchanged. Containment isolates latent defects in newly inspected units; each inspection adds 0.6 minutes and 2 cost, exposing delivery.");
    } else if (card.id === "protect-dispatch") {
      card.title = t("Choose a dispatch priority");
      card.detail = t("Orders share a delivery window. Priority changes the allocation order when finished goods are scarce; it can protect one customer while exposing another.");
    } else if (card.id === "protect-customer") {
      const order = [...s.order_summary.orders].sort((a, b) => a.due_minute - b.due_minute || a.id.localeCompare(b.id)).find(o => o.remaining_quantity > 0);
      if (order) {
        card.title = t("Protect {order}", { order: order.id });
        card.detail = t("{units} units remain due at minute {minute}. Current delivery outlook: {risk}. Priority changes only same-deadline allocation; protecting one order may expose another.", { units: order.remaining_quantity, minute: order.due_minute, risk: p.scene.order_risks[order.id] });
      }
    } else if (card.id === "shift-extension") {
      card.title = t("Consider one overtime extension");
      card.detail = t("60 extra production minutes / 600 labor cost. Failure exposure increases 20% only during overtime. Authorize before shift close; due dates remain unchanged.");
    }
  }
  const review = p.shift_review;
  const downtime = Object.values(s.machine_metrics).reduce((sum, m) => sum + m.unplanned_downtime_minutes, 0).toFixed(1);
  const failures = Object.values(s.machine_metrics).reduce((sum, m) => sum + m.failures, 0);
  review.headline = text(review.headline);
  if (review.state === "final") review.conclusion = t("Observed outcome: {delivered} units delivered, {backlog} backlog, {scrap} scrap and {downtime} summed machine downtime minutes. The review records observed outcomes; it does not infer that one action alone caused them. Use the action log together with the machine and order history in the next shift handover.", { delivered: s.order_summary.units_delivered, backlog: s.order_summary.backlog_units, scrap: s.scrap, downtime });
  else review.conclusion = text(review.conclusion);
  for (const item of review.scorecard) {
    item.label = text(item.label);
    if (item.id === "delivery") item.value = s.order_summary.orders_due && s.order_summary.otif !== null ? t("OTIF {otif} across {orders} due orders", { otif: pct(s.order_summary.otif), orders: s.order_summary.orders_due }) : t(review.state === "final" ? "No customer order became due" : "No customer order due yet");
    else if (item.id === "quality") item.value = s.machine_metrics.quality_01.processed ? t("{quality} inspection yield · {scrap} scrap · {escapes} customer escapes", { quality: pct(s.quality, 1), scrap: s.scrap, escapes: session.quality_containment?.customer_escapes ?? 0 }) : t("No inspections completed yet");
    else if (item.id === "resilience") item.value = t("{failures} failure(s) · {downtime} unplanned min", { failures, downtime });
    else if (item.id === "cost") item.value = t("{cost} material, maintenance, expediting, labor and inspection", { cost: session.cost_breakdown.total.toFixed(2) });
  }
  for (const action of [...session.action_log, ...session.maintenance_history]) {
    const service = action.machine_id ? s.machine_metrics[action.machine_id]?.service : null;
    if (!service) continue;
    const values = { service: service.label, cost: service.cost, duration: service.duration };
    if (action.kind === "EQUIPMENT_SERVICE_REQUESTED") action.detail = t("{service} requested: {cost} cost; finish current unit before {duration}-minute stop", values);
    else if (action.kind === "EQUIPMENT_SERVICE_STARTED") action.detail = t("{service}: production stopped for {duration} minutes", values);
    else if (action.kind === "EQUIPMENT_SERVICE_COMPLETED") action.detail = t("{service} complete: condition restored; normal cycles resume", values);
  }
  for (const row of session.timeline) {
    const event = session.shift_events?.find(e => e.id === row.id);
    const order = s.order_summary.orders.find(o => `due-${o.id}` === row.id);
    const po = s.supply_summary.purchase_orders.find(o => `receipt-${o.id}` === row.id);
    const action = session.action_log.find(a => `action-${a.id}` === row.id);
    const maintenance = session.maintenance_history.find(a => `equipment-${a.id}` === row.id);
    if (event) row.title = event.title;
    else if (order) row.title = t("{value1} due", { value1: order.id });
    else if (po) row.title = t("{order} receipt", { order: po.id });
    else if (maintenance) row.title = `${maintenance.machine_id?.replace("_", "-").toUpperCase()}: ${maintenance.detail || maintenance.kind}`;
    else if (action) row.title = action.kind; // Event codes remain technical identifiers.
  }
  return session;
}
