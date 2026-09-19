import { clock } from "../format";
import { useI18n } from "../i18n";
import type { PlantSession } from "../hooks/usePlantSession";
import type { Workspace } from "../types";

export function ShiftDecisions({ control, workspace }: { control: PlantSession; workspace: Workspace }) {
  const { t, label } = useI18n();
  const session = control.session;
  if (!session) return null;
  const minute = session.summary.simulated_minutes;
  const events = session.shift_events?.filter(e => e.state === "active" && (e.choices?.length || e.kind === "management_objective") && (workspace === "Office / Inbox" || workspace === e.workspace)) ?? [];
  if (!events.length) return null;
  return <section className="work-section shift-decisions" aria-label={t("Live decisions")}>
    <h2>{t("Live decisions")}</h2>
    {events.map(event => <article className="shift-decision" key={event.id}>
      <div className="section-title"><strong><span className={`signal ${event.severity}`} />{event.title}</strong><span>{label(event.severity)}</span></div>
      <p>{event.detail}</p><small>{t("From: Shift manager")} · {event.affected_ids.join(", ")} · {clock(event.start_minute ?? event.minute)}</small>
      {event.kind === "management_objective" && session.management_objective && <p>{t("Management target")}: {session.management_objective.target_id} · {session.management_objective.kind === "throughput" ? session.management_objective.target : t("Complete on time")} · {label(session.management_objective.status)}</p>}
      {!!event.choices?.length && <>
        <p className="decision-deadline">{t("Decision due at {time} · {minutes} simulated minutes remaining", { time: clock(event.deadline_minute ?? event.end_minute), minutes: Math.max(0, Math.ceil((event.deadline_minute ?? event.end_minute) - minute)) })}</p>
        <div className="decision-options">{event.choices.map(choice => <div key={choice.id}><button data-decision-action disabled={!!control.busy || !!choice.unavailable_reason || minute >= (event.deadline_minute ?? event.end_minute) || minute >= session.summary.shift_minutes} onClick={() => void control.decide(event.id, choice.id)}>{choice.label}</button><small>{t("Immediate commitment: {cost}", { cost: choice.cost })}</small><p>{choice.expected}</p>{choice.unavailable_reason && <small>{choice.unavailable_reason}</small>}</div>)}</div>
        <p className="table-note">{t("Waiting is a decision.")} {event.no_action}</p>
        {event.pressure !== undefined && <small>{t("Pressure factor: {pressure} · operational window ends at {time}", { pressure: event.pressure.toFixed(2), time: clock(event.effect_until ?? event.end_minute) })}</small>}
      </>}
    </article>)}
  </section>;
}
