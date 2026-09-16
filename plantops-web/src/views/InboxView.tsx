import type { SessionSnapshot, Workspace } from "../types";
import { clock } from "../format";
export function InboxView({session, navigate}: {session: SessionSnapshot; navigate: (view: Workspace) => void}) {
  const profile = session.scenario_profile;
  return <div className="office-view"><div className="view-heading"><h1>Office / Inbox</h1><span>Shift handover · {clock(session.summary.simulated_minutes)}</span></div>
    <article className="briefing-letter"><div className="memo-meta"><span>From: Shift manager</span><span>To: Industrial engineering</span><span>00:00 · Handover</span></div><h2>{profile.title}</h2><p>{profile.briefing}</p><p>Starting condition: {profile.initial_conditions.raw_units} steel blanks, {Object.values(profile.initial_conditions.wip).reduce((a, b) => a + b, 0)} carried-in WIP units, CNC health {profile.initial_conditions.machine_health.cnc_01}/100.</p><button onClick={() => navigate("Plant View")}>Inspect the line</button></article>
    <section className="work-section"><h2>Current engineering tasks</h2><p>Tasks follow live operational concerns. They clear as the underlying condition changes.</p><ul className="task-list">{profile.active_alerts.map(alert => <li key={alert.id}><span className={`signal ${alert.severity}`}/><div><strong>{alert.workspace}</strong><p>{alert.message}</p></div><button onClick={() => navigate(alert.workspace)}>Review</button></li>)}</ul>{!profile.active_alerts.length && <p>No active exceptions. Monitor delivery progress as the shift advances.</p>}</section>
    <section className="work-section"><h2>Production-control note</h2><p>Priorities decide ties between orders with the same due time. Material is allocated automatically from finished goods. All costs and decisions remain attached to this shift.</p></section>
  </div>;
}
