import type { PlantSession } from "../hooks/usePlantSession";
import type { Workspace } from "../types";
import { money } from "../format";

export function Coach({step, control, view, navigate, skip, runFirst, review, replay}: {
  step: number; control: PlantSession; view: Workspace; navigate: (view: Workspace) => void;
  skip: () => void; runFirst: () => void; review: () => void; replay: () => void;
}) {
  const s = control.session!;
  const laser = s.summary.machine_metrics.laser_01;
  const cost = s.cost_breakdown.lens_gas_cleaning ?? 0;
  const titles = ["Read the shift handover", "Protect the customer commitment", "Inspect LASER-01", "Weigh the service decision", "Observe the shift in motion", "Measure the operational result", "First shift reviewed"];
  return <section className="tutorial-coach" aria-label="Guided shift coaching">
    <div className="tutorial-heading"><strong>Guided shift · Step {step} of 7</strong><button onClick={skip}>{step === 7 ? "Continue this shift" : step === 1 && s.summary.simulated_minutes > 0 ? "Exit tutorial" : "Skip tutorial"}</button></div>
    <h2>{titles[step - 1]}</h2>
    {step === 1 && <>{s.summary.simulated_minutes > 0 && <p>This shift is already underway. <button onClick={() => navigate("Office / Inbox")}>Resume tutorial</button> by reopening the handover, or exit coaching to keep playing.</p>}<p>Your supervisor left a cutting-condition concern. Open the first-shift handover in Office / Inbox before making a decision.</p>{view !== "Office / Inbox" && <button onClick={() => navigate("Office / Inbox")}>Open Office / Inbox</button>}</>}
    {step === 2 && <><p>The priority order needs 30 brackets by minute 50. Quantity, due time and quality all matter. Look at the route and waiting material.</p><button onClick={() => navigate("Plant View")}>Open Plant View</button></>}
    {step === 3 && <><p>Select LASER-01 on the plan. CNC health is better when higher; laser contamination burden is better when lower. Cutting currently has {s.summary.buffer_levels.raw} queued blanks, {laser.condition_value?.toFixed(1)}/100 contamination and a {laser.cycle_time_multiplier?.toFixed(2)}× cycle multiplier.</p>{view !== "Plant View" && <button onClick={() => navigate("Plant View")}>Return to Plant View</button>}</>}
    {step === 4 && <><p>Service consumes 8 minutes and 85 cost. Ignoring contamination can mean slower cutting and edge rejects. Review Maintenance; choose service there, or deliberately run first.</p><button onClick={() => navigate("Maintenance")}>Open Maintenance</button> <button onClick={runFirst}>Run production first</button></>}
    {step === 5 && <><p>Use Start shift to advance, Pause to hold, and 2× or 4× to change playback speed. Observe at least 20 simulated minutes and let any service finish. This card follows engine time, not a countdown.</p><p>Minute {s.summary.simulated_minutes.toFixed(1)} · {laser.processed} cut · {laser.scrap} cutting rejects · {laser.service?.active ? "Lens service in progress" : laser.service?.pending ? "Lens service queued" : laser.active_issue ?? "Cutting condition within limits"}.</p></>}
    {step === 6 && <><p>Lens service: {money(cost)} committed. Released: {s.summary.good_production}; backlog: {s.summary.order_summary.backlog_units} of 30 initial units. All-stage scrap: {s.summary.total_scrap ?? s.summary.scrap}. Laser burden: {laser.condition_value?.toFixed(1)}/100.</p><p>{cost > 0 ? "Service traded a planned stop and cost for lower contamination. Check the recovery record and what the order still needs." : "You ran without lens service. Compare the remaining contamination, actual cutting rejects and delivery progress; no rejects yet does not mean no exposure."} One action does not guarantee a good shift.</p>{!["Reports", "Quality"].includes(view) ? <button onClick={() => navigate("Reports")}>Review Reports</button> : <button onClick={review}>I’ve reviewed these results</button>}</>}
    {step === 7 && <><p>You used a handover, checked the factory state, {cost > 0 ? "made an intervention" : "chose to observe production before servicing"}, and measured the result. Carry that loop into your next shift.</p><button disabled={!!control.busy} onClick={() => void control.newShift(42)}>Start a new seeded shift</button> <button disabled={!!control.busy} onClick={replay}>Replay tutorial</button></>}
  </section>;
}
