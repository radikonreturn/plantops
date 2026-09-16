import type { PlantSession } from "../hooks/usePlantSession";
import { OrderBoard } from "../components/OrderBoard";
export function ProductionPlanView({control}: {control: PlantSession}) {
  const session = control.session!;
  const {summary, scenario_profile: profile} = session;
  return <div className="office-view"><div className="view-heading"><h1>Production Plan</h1><span>One product family · finite buffers</span></div>
    <dl className="readings horizontal"><div><dt>Customer target</dt><dd>{summary.order_summary.units_ordered} units</dd></div><div><dt>Good production</dt><dd>{summary.good_production} units</dd></div><div><dt>Ideal shift capacity</dt><dd>{profile.capacity.ideal_shift_units} units</dd></div><div><dt>Bottleneck cycle</dt><dd>{profile.capacity.bottleneck_cycle_minutes} min/unit</dd></div></dl>
    <p className="table-note">{profile.capacity.estimate_note} Target includes scheduled urgent demand; this is a planning view, not a forecast.</p>
    <section className="work-section"><h2>Line capacity context</h2><div className="table-scroll"><table><thead><tr><th>Stage</th><th>Ideal cycle</th><th>Processed</th><th>Input queue</th><th>Output queue</th></tr></thead><tbody>{profile.machines.map(asset => <tr key={asset.id}><td>{asset.name}</td><td>{asset.ideal_cycle_minutes} min</td><td>{summary.machine_metrics[asset.id].processed}</td><td>{summary.buffer_levels[asset.input_buffer]}</td><td>{asset.output_buffer === "finished" ? summary.finished_goods_available : summary.buffer_levels[asset.output_buffer]}</td></tr>)}</tbody></table></div></section>
    <OrderBoard session={session} busy={!!control.busy} save={control.prioritize}/>
  </div>;
}
