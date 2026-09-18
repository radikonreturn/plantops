import { clock } from "../format";
import { workspaces, type SessionSnapshot, type Workspace } from "../types";
export function LeftRail({session, view, navigate}: {session: SessionSnapshot | null; view: Workspace; navigate: (view: Workspace) => void}) {
  const s = session?.summary;
  const shiftMinutes = s?.shift_minutes ?? 480;
  const elapsed = s?.simulated_minutes ?? 0;
  const timeline = session?.timeline ?? [];
  const recent = timeline.filter(e => e.minute <= elapsed && !["scheduled", "PENDING"].includes(e.state) && !e.id.startsWith("due-") && !e.id.startsWith("receipt-")).slice(-4);
  const events = [...recent, ...timeline.filter(e => !recent.some(r => r.id === e.id) && (e.state === "active" || e.minute > elapsed)).slice(0, 7)].map(e => ({...e, text: e.title}));
  return <aside className="left-rail">
    <section className="rail-timeline"><h2>Shift timeline</h2><div className="timeline-scale" aria-label={`Current shift time ${clock(elapsed)} of ${clock(shiftMinutes)}`}>
      {events.map(event => <i key={event.id} title={`${event.text}: ${clock(event.minute)}`} style={{left: `${Math.min(100, event.minute / shiftMinutes * 100)}%`}} />)}
      <span style={{left: `${Math.min(100, elapsed / shiftMinutes * 100)}%`}} className="time-marker" />
    </div><div className="timeline-track">
      <div><b>00:00</b><span>Shift handover</span></div>{events.map(event => <div key={event.id}><b>{clock(event.minute)}</b><button onClick={() => navigate(event.workspace)}>{event.text}<small>{event.state}</small></button></div>)}<div><b>{clock(s?.shift_minutes ?? 480)}</b><span>Shift close</span></div>
    </div><p className="rail-clock">Now {clock(s?.simulated_minutes ?? 0)} · {session?.paused ? "Paused" : "Running"}</p></section>
    <section className="rail-alerts"><h2>Active alerts <span>{session?.scenario_profile.active_alerts.length ?? 0}</span></h2>{session?.scenario_profile.active_alerts.slice(0, 3).map(alert => <button className={`rail-alert ${alert.severity}`} key={alert.id} onClick={() => navigate(alert.workspace)}><span className="signal" />{alert.message}</button>)}{session && !session.scenario_profile.active_alerts.length && <p>No active exceptions.</p>}</section>
    <nav aria-label="Engineering workspace"><h2>ENGINEERING WORKSPACE</h2>{workspaces.map((item, index) => <button key={item} data-workspace={item} aria-current={view === item ? "page" : undefined} onClick={() => navigate(item)}><svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="3" width="14" height="14" rx="1"/><path d={index === 0 ? "M3 10h14M10 3v14" : index === 4 ? "M6 14l8-8M6 6l8 8" : "M6 7h8M6 10h8M6 13h5"}/></svg>{item}</button>)}</nav>
    <div className="rail-footer">Single product family<br/>Shift {s?.seed ?? "—"} · Local session</div>
  </aside>;
}
