import type { SessionSnapshot } from "../types";
import { clock, label, money, percent } from "../format";
export function ReportsView({session}: {session: SessionSnapshot}) {
  const s = session.summary;
  const rows = [
    ["Good production", `${s.good_production} / ${s.order_summary.units_ordered} customer units`],
    ["OEE", percent(s.oee)], ["Observed quality yield", s.machine_metrics.quality_01.processed ? percent(s.quality) : "No inspections yet"],
    ["Scrap", s.scrap], ["OTIF", percent(s.order_summary.otif)], ["Backlog", `${s.order_summary.backlog_units} units / ${s.order_summary.backlog_orders} orders`],
    ["Unplanned downtime (sum across machines)", `${Object.values(s.machine_metrics).reduce((sum, m) => sum + m.unplanned_downtime_minutes, 0).toFixed(1)} min`],
    ["Planned maintenance (sum across machines)", `${Object.values(s.machine_metrics).reduce((sum, m) => sum + m.planned_maintenance_minutes, 0).toFixed(1)} min`],
    ["Emergency repair cost", money(session.intervention_cost)], ["Preventive maintenance cost", money(session.preventive_maintenance_cost)],
    ["Procurement committed cost", money(s.supply_summary.procurement_committed_cost)],
  ];
  return <div className="office-view"><div className="view-heading"><h1>Reports</h1><span>{s.simulated_minutes >= s.shift_minutes ? "Shift-end report" : "Interim shift report"} · {clock(s.simulated_minutes)}</span></div>
    <h2>{session.scenario_profile.title}</h2><div className="report-grid"><dl className="report-readings">{rows.map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl><section><h2>Open risks at report time</h2>{session.scenario_profile.active_alerts.map(alert => <p key={alert.id}>{alert.message}</p>)}{!session.scenario_profile.active_alerts.length && <p>No active concerns.</p>}<p className="table-note">OTIF includes only due orders and counts those completed by their deadline. No due orders means no score. Summed machine downtime is not line downtime.</p></section></div>
    <section className="work-section"><h2>Equipment performance</h2><div className="table-scroll"><table><thead><tr><th>Machine</th><th>Processed</th><th>Health</th><th>Failures</th><th>Unplanned stop</th><th>Planned stop</th><th>Availability</th></tr></thead><tbody>{session.scenario_profile.machines.map(asset => {const m = s.machine_metrics[asset.id]; return <tr key={asset.id}><td>{asset.name}</td><td>{m.processed}</td><td>{m.health.toFixed(1)}</td><td>{m.failures}</td><td>{m.unplanned_downtime_minutes.toFixed(1)} min</td><td>{m.planned_maintenance_minutes.toFixed(1)} min</td><td>{percent(m.availability)}</td></tr>;})}</tbody></table></div></section>
    <section className="work-section"><h2>Player action log</h2><div className="table-scroll"><table><thead><tr><th>Minute</th><th>Action</th><th>Asset / detail</th></tr></thead><tbody>{session.action_log.map(action => <tr key={action.id}><td>{action.minute.toFixed(1)}</td><td>{label(action.kind)}</td><td className="log-detail">{action.machine_id ? `${action.machine_id} · ` : ""}{action.detail || "Emergency crew completed the repair."}</td></tr>)}{!session.action_log.length && <tr><td colSpan={3}>No production decisions recorded yet.</td></tr>}</tbody></table></div></section>
    <p className="digest">Replay seed {s.seed} · Profile {session.scenario_profile.id}<br/>Event digest {session.event_digest}</p>
  </div>;
}
