import { useI18n } from "../i18n";
import type { SessionSnapshot } from "../types";
import { clock } from "../format";
export function ReportsView({session}: {session: SessionSnapshot}) {
  const { t, label, money, percent } = useI18n();
  const s = session.summary;
  const rows = [
    [t("Good production"), t("{value1} / {value2} customer units", {value1: s.good_production, value2: s.order_summary.units_ordered})],
    ["OEE", percent(s.oee)], [t("Observed quality yield"), s.machine_metrics.quality_01.processed ? percent(s.quality) : t("No inspections yet")],
    [t("All-stage scrap"), s.total_scrap ?? s.scrap], ["OTIF", percent(s.order_summary.otif)], [t("Backlog"), t("{value1} units / {value2} orders", {value1: s.order_summary.backlog_units, value2: s.order_summary.backlog_orders})],
    [t("Unplanned downtime (sum across machines)"), t("{value1} min", {value1: Object.values(s.machine_metrics).reduce((sum, m) => sum + m.unplanned_downtime_minutes, 0).toFixed(1)})],
    [t("Planned maintenance (sum across machines)"), t("{value1} min", {value1: Object.values(s.machine_metrics).reduce((sum, m) => sum + m.planned_maintenance_minutes, 0).toFixed(1)})],
    [t("Emergency repair cost"), money(session.intervention_cost)], [t("Preventive maintenance cost"), money(session.preventive_maintenance_cost)],
    [t("Lens / gas cleaning"), money(session.cost_breakdown.lens_gas_cleaning ?? 0)],
    [t("Chemical / filter service"), money(session.cost_breakdown.chemical_filter_service ?? 0)],
    [t("Support labor"), money(session.cost_breakdown.support_labor ?? 0)],
    [t("Tester calibration"), money(session.cost_breakdown.tester_calibration ?? 0)],
    [t("Rework / retests"), s.equipment_quality?.rework ?? 0],
    [t("Expedite cost"), money(session.cost_breakdown.expediting)],
    [t("Overtime labor cost"), money(session.cost_breakdown.overtime)],
    [t("Inspection cost"), money(session.cost_breakdown.inspection)],
    [t("Total committed cost"), money(session.cost_breakdown.total)],
    [t("Customer escapes"), session.quality_containment?.customer_escapes ?? t("Not modeled in classic")],
    [t("Suspect unallocated finished goods"), session.quality_containment?.suspect_finished_units ?? t("Not modeled in classic")],
    [t("Procurement committed cost"), money(s.supply_summary.procurement_committed_cost)],
  ];
  return <div className="office-view"><div className="view-heading"><h1>{t("Reports")}</h1><span>{s.simulated_minutes >= s.shift_minutes ? t("Shift-end report") : t("Provisional interim report")} · {clock(s.simulated_minutes)}</span></div>
    <section className="manager-review"><div><span className="eyebrow">{session.scenario_profile.shift_review.state === "final" ? t("Management close-out") : t("Management checkpoint")}</span><h2>{session.scenario_profile.shift_review.headline}</h2><p>{session.scenario_profile.shift_review.conclusion}</p></div><span className="review-actions">{t("{value1} decision{value2} recorded", {value1: session.scenario_profile.shift_review.actions_recorded, value2: session.scenario_profile.shift_review.actions_recorded === 1 ? "" : "s"})}</span></section>
    <div className="review-scorecard">{session.scenario_profile.shift_review.scorecard.map(item => <section className={`review-metric ${item.status}`} key={item.id}><span>{item.label}</span><strong>{item.value}</strong></section>)}</div>
    <h2>{session.scenario_profile.title}</h2><div className="report-grid"><dl className="report-readings">{rows.map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl><section><h2>{t("Open risks at report time")}</h2>{session.scenario_profile.active_alerts.map(alert => <p key={alert.id}>{alert.message}</p>)}{!session.scenario_profile.active_alerts.length && <p>{t("No active concerns.")}</p>}<p className="table-note">{t("Good production and yield retain the legacy inspection-release definition; latent customer escapes are shown separately and do not retroactively reduce OTIF. OTIF includes only due orders and counts those completed by their deadline. No due orders means no score. Summed machine downtime is not line downtime.")}</p></section></div>
    <section className="work-section"><h2>{t("Equipment performance")}</h2><div className="table-scroll"><table><thead><tr><th>{t("Machine")}</th><th>{t("Processed")}</th><th>{t("Health")}</th><th>{t("Failures")}</th><th>{t("Unplanned stop")}</th><th>{t("Planned stop")}</th><th>{t("Availability")}</th></tr></thead><tbody>{session.scenario_profile.machines.map(asset => {const m = s.machine_metrics[asset.id]; return <tr key={asset.id}><td>{asset.name}</td><td>{m.processed}</td><td>{m.health.toFixed(1)}</td><td>{m.failures}</td><td>{t("{value1} min", {value1: m.unplanned_downtime_minutes.toFixed(1)})}</td><td>{t("{value1} min", {value1: m.planned_maintenance_minutes.toFixed(1)})}</td><td>{percent(m.availability)}</td></tr>;})}</tbody></table></div></section>
    <section className="work-section"><h2>{t("Shift event history")}</h2><div className="table-scroll"><table><thead><tr><th>{t("Minute")}</th><th>{t("Event / owner")}</th><th>{t("Lifecycle")}</th><th>{t("Modeled consequence")}</th></tr></thead><tbody>{session.shift_events?.map(e => <tr key={e.id}><td>{e.minute}</td><td>{e.title}<small>{t(e.workspace)} · {e.zone}</small></td><td>{label(e.state)}{e.closed_minute !== null && <small>{t("At {value1}", {value1: clock(e.closed_minute)})}</small>}</td><td>{e.detail}{e.affected_ids.length > 0 && <small>{e.affected_ids.join(", ")}</small>}</td></tr>)}</tbody></table></div></section>
    <section className="work-section"><h2>{t("Player action log")}</h2><div className="table-scroll"><table><thead><tr><th>{t("Minute")}</th><th>{t("Action")}</th><th>{t("Asset / detail")}</th></tr></thead><tbody>{session.action_log.map(action => <tr key={action.id}><td>{action.minute.toFixed(1)}</td><td>{label(action.kind)}</td><td className="log-detail">{action.machine_id ? `${action.machine_id} · ` : ""}{action.detail || t("Emergency crew completed the repair.")}</td></tr>)}{!session.action_log.length && <tr><td colSpan={3}>{t("No production decisions recorded yet.")}</td></tr>}</tbody></table></div></section>
    <p className="digest">{t("Replay seed {value1} · Profile {value2}", {value1: s.seed, value2: session.scenario_profile.id})}<br/>{t("Event digest {value1}", {value1: session.event_digest})}</p>
  </div>;
}
