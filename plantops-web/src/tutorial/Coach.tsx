import { useI18n } from "../i18n";
import type { PlantSession } from "../hooks/usePlantSession";
import type { Workspace } from "../types";

export function Coach({step, control, view, navigate, skip, runFirst, review, replay}: {
  step: number; control: PlantSession; view: Workspace; navigate: (view: Workspace) => void;
  skip: () => void; runFirst: () => void; review: () => void; replay: () => void;
}) {
  const { t, money } = useI18n();
  const s = control.session!;
  const laser = s.summary.machine_metrics.laser_01;
  const cost = s.cost_breakdown.lens_gas_cleaning ?? 0;
  const titles = [t("Read the shift handover"), t("Protect the customer commitment"), t("Inspect LASER-01"), t("Weigh the service decision"), t("Observe the shift in motion"), t("Measure the operational result"), t("First shift reviewed")];
  return <section className="tutorial-coach" aria-label={t("Guided shift coaching")}>
    <div className="tutorial-heading"><strong>{t("Guided shift · Step {value1} of 7", {value1: step})}</strong><button onClick={skip}>{step === 7 ? t("Continue this shift") : step === 1 && s.summary.simulated_minutes > 0 ? t("Exit tutorial") : t("Skip tutorial")}</button></div>
    <progress className="tutorial-progress" aria-label={t("Tutorial progress")} max={7} value={step}/>
    <p className="tutorial-mode-note">{t("Practice scenario · guided difficulty")}</p>
    <h2>{titles[step - 1]}</h2>
    {step === 1 && <>{s.summary.simulated_minutes > 0 && <p>{t("This shift is already underway.") + " "}<button onClick={() => navigate("Office / Inbox")}>{t("Resume tutorial")}</button>{" " + t("by reopening the handover, or exit coaching to keep playing.")}</p>}<p>{t("Your supervisor left a cutting-condition concern. Open the first-shift handover in Office / Inbox before making a decision.")}</p>{view !== "Office / Inbox" && <button onClick={() => navigate("Office / Inbox")}>{t("Open Office / Inbox")}</button>}</>}
    {step === 2 && <><p>{t("The priority order needs 30 brackets by minute 50. Quantity, due time and quality all matter. Look at the route and waiting material.")}</p><button onClick={() => navigate("Plant View")}>{t("Open Plant View")}</button></>}
    {step === 3 && <><p>{t("Select LASER-01 on the plan. CNC health is better when higher; laser contamination burden is better when lower. Cutting currently has {value1} queued blanks, {value2}/100 contamination and a {value3}× cycle multiplier.", {value1: s.summary.buffer_levels.raw, value2: laser.condition_value?.toFixed(1), value3: laser.cycle_time_multiplier?.toFixed(2)})}</p>{view !== "Plant View" && <button onClick={() => navigate("Plant View")}>{t("Return to Plant View")}</button>}</>}
    {step === 4 && <><p>{t("Service consumes 8 minutes and 85 cost. Ignoring contamination can mean slower cutting and edge rejects. Review Maintenance; choose service there, or deliberately run first.")}</p><button onClick={() => navigate("Maintenance")}>{t("Open Maintenance")}</button> <button onClick={runFirst}>{t("Run production first")}</button></>}
    {step === 5 && <><p>{t("Use Start shift to advance, Pause to hold, and 2× or 4× to change playback speed. Observe at least 20 simulated minutes and let any service finish. This card follows engine time, not a countdown.")}</p><p>{t("Minute {value1} · {value2} cut · {value3} cutting rejects · {value4}.", {value1: s.summary.simulated_minutes.toFixed(1), value2: laser.processed, value3: laser.scrap, value4: laser.service?.active ? t("Lens service in progress") : laser.service?.pending ? t("Lens service queued") : laser.active_issue ?? t("Cutting condition within limits")})}</p></>}
    {step === 6 && <><p>{t("Lens service: {value1} committed. Released: {value2}; backlog: {value3} of 30 initial units. All-stage scrap: {value4}. Laser burden: {value5}/100.", {value1: money(cost), value2: s.summary.good_production, value3: s.summary.order_summary.backlog_units, value4: s.summary.total_scrap ?? s.summary.scrap, value5: laser.condition_value?.toFixed(1)})}</p><p>{t("{value1} One action does not guarantee a good shift.", {value1: cost > 0 ? t("Service traded a planned stop and cost for lower contamination. Check the recovery record and what the order still needs.") : t("You ran without lens service. Compare the remaining contamination, actual cutting rejects and delivery progress; no rejects yet does not mean no exposure.")})}</p>{!["Reports", "Quality"].includes(view) ? <button onClick={() => navigate("Reports")}>{t("Review Reports")}</button> : <button onClick={review}>{t("I’ve reviewed these results")}</button>}</>}
    {step === 7 && <><p>{t("You used a handover, checked the factory state, {value1}, and measured the result. Carry that loop into your next shift.", {value1: cost > 0 ? t("made an intervention") : t("chose to observe production before servicing")})}</p><button disabled={!!control.busy} onClick={() => void control.newShift(42)}>{t("Start a new seeded shift")}</button> <button disabled={!!control.busy} onClick={replay}>{t("Replay tutorial")}</button></>}
  </section>;
}
