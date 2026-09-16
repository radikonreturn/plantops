import type { SessionSnapshot } from "../types";
import { percent } from "../format";
export function QualityView({session}: {session: SessionSnapshot}) {
  const s = session.summary;
  const quality = s.machine_metrics.quality_01;
  const stage = session.scenario_profile.machines.find(m => m.id === "quality_01")!;
  return <div className="office-view"><div className="view-heading"><h1>Quality</h1><span>Automatic final inspection · read only</span></div>
    <dl className="readings horizontal"><div><dt>Inspected units</dt><dd>{quality.processed}</dd></div><div><dt>Accepted</dt><dd>{s.good_production}</dd></div><div><dt>Scrapped</dt><dd>{s.scrap}</dd></div><div><dt>Observed yield</dt><dd>{quality.processed ? percent(s.quality) : "No inspections yet"}</dd></div><div><dt>Configured lot reject risk</dt><dd>{percent(stage.scrap_probability)}</dd></div></dl>
    <section className="work-section"><h2>Inspection disposition</h2><div className="table-scroll"><table><thead><tr><th>Disposition</th><th>Actual units</th><th>Consequence</th></tr></thead><tbody><tr><td>Accepted</td><td>{s.good_production}</td><td>Received into finished goods and made available for customer allocation.</td></tr><tr><td>Non-conforming / scrapped</td><td>{s.scrap}</td><td>Removed from production; cannot satisfy customer orders.</td></tr></tbody></table></div><p>Every completed Quality cycle makes a seeded inspection decision. The event log records rejected units. The lot risk is a scenario parameter; observed yield is calculated from actual inspection outcomes.</p></section>
    <section className="work-section"><h2>Quality concerns</h2>{session.scenario_profile.active_alerts.filter(a => a.workspace === "Quality").map(a => <p key={a.id}>{a.message}</p>)}<p>Manual containment, reinspection and corrective-action submissions are deferred. This screen reports the automatic inspection record and does not imply an unimplemented release workflow.</p></section>
  </div>;
}
