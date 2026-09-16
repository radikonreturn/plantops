import type { PlantSession } from "../hooks/usePlantSession";
import { OrderBoard } from "../components/OrderBoard";
export function ProductionPlanView({control}: {control: PlantSession}) {
  const session = control.session!;
  const {summary, scenario_profile: profile} = session;
  return <div className="office-view"><div className="view-heading"><h1>Production Plan</h1><span>One product family · finite buffers</span></div>
    <dl className="readings horizontal"><div><dt>Customer target</dt><dd>{summary.order_summary.units_ordered} units</dd></div><div><dt>Good production</dt><dd>{summary.good_production} units</dd></div><div><dt>Ideal shift capacity</dt><dd>{profile.capacity.ideal_shift_units} units</dd></div><div><dt>Bottleneck cycle</dt><dd>{profile.capacity.bottleneck_cycle_minutes} min/unit</dd></div></dl>
    <p className="table-note">{profile.capacity.estimate_note} Target includes scheduled urgent demand; this is a planning view, not a forecast.</p>
    {session.overtime && <section className="work-section"><h2>Shift extension</h2><p>Authorize once before close: 60 extra minutes / 600 labor cost. Failure exposure rises 20% during overtime only; customer deadlines stay fixed.</p><button disabled={!!control.busy || !!session.overtime.unavailable_reason} onClick={() => void control.overtime()}>Authorize overtime · 600</button><p>{session.overtime.unavailable_reason ?? "Available until normal shift close"} · {session.overtime.fatigue_active ? "Fatigue exposure active" : "Normal failure exposure"}</p></section>}
    <section className="work-section"><h2>Line capacity context</h2><div className="table-scroll"><table><thead><tr><th>Stage</th><th>Ideal cycle / capacity</th><th>Processed</th><th>Input queue</th><th>Output queue</th></tr></thead><tbody>{profile.machines.map(asset => <tr key={asset.id}><td>{asset.name}</td><td>{asset.ideal_cycle_minutes} min · {(60 / asset.ideal_cycle_minutes).toFixed(1)}/h{profile.capacity.bottleneck_machines.includes(asset.id) && <small>Configured capacity limit</small>}</td><td>{summary.machine_metrics[asset.id].processed}</td><td>{summary.buffer_levels[asset.input_buffer]} / {profile.scene.zones.find(z => z.id === asset.input_buffer)?.capacity ?? "uncapped"}<small>{asset.input_buffer}</small></td><td>{asset.output_buffer === "finished" ? summary.finished_goods_available : summary.buffer_levels[asset.output_buffer]}<small>{asset.output_buffer}</small></td></tr>)}</tbody></table></div></section>
    <OrderBoard session={session} busy={!!control.busy} save={control.prioritize}/>
  </div>;
}
