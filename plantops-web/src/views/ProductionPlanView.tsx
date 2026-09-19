import { useI18n } from "../i18n";
import type { PlantSession } from "../hooks/usePlantSession";
import { OrderBoard } from "../components/OrderBoard";
export function ProductionPlanView({control}: {control: PlantSession}) {
  const { t } = useI18n();
  const session = control.session!;
  const {summary, scenario_profile: profile} = session;
  return <div className="office-view"><div className="view-heading"><h1>{t("Production Plan")}</h1><span>{t("One product family · finite buffers")}</span></div>
    <dl className="readings horizontal"><div><dt>{t("Customer target")}</dt><dd>{t("{value1} units", {value1: summary.order_summary.units_ordered})}</dd></div><div><dt>{t("Good production")}</dt><dd>{t("{value1} units", {value1: summary.good_production})}</dd></div><div><dt>{t("Ideal shift capacity")}</dt><dd>{t("{value1} units", {value1: profile.capacity.ideal_shift_units})}</dd></div><div><dt>{t("Bottleneck cycle")}</dt><dd>{t("{value1} min/unit", {value1: profile.capacity.bottleneck_cycle_minutes})}</dd></div></dl>
    <p className="table-note">{t("{value1} Target includes scheduled urgent demand; this is a planning view, not a forecast.", {value1: profile.capacity.estimate_note})}</p>
    {session.overtime && <section className="work-section"><h2>{t("Shift extension")}</h2><p>{t("Authorize once before close: 60 extra minutes / 600 labor cost. Failure exposure rises 20% during overtime only; customer deadlines stay fixed.")}</p><button disabled={!!control.busy || !!session.overtime.unavailable_reason} onClick={() => void control.overtime()}>{t("Authorize overtime · 600")}</button><p>{session.overtime.unavailable_reason ?? t("Available until normal shift close")} · {session.overtime.fatigue_active ? t("Fatigue exposure active") : t("Normal failure exposure")}</p></section>}
    <section className="work-section"><h2>{t("Line capacity context")}</h2><div className="table-scroll"><table><thead><tr><th>{t("Stage")}</th><th>{t("Ideal cycle / capacity")}</th><th>{t("Processed")}</th><th>{t("Input queue")}</th><th>{t("Output queue")}</th></tr></thead><tbody>{profile.machines.map(asset => <tr key={asset.id}><td>{asset.name}</td><td>{asset.ideal_cycle_minutes}{" " + t("min ·") + " "}{(60 / asset.ideal_cycle_minutes).toFixed(1)}{t("/h")}{profile.capacity.bottleneck_machines.includes(asset.id) && <small>{t("Configured capacity limit")}</small>}</td><td>{summary.machine_metrics[asset.id].processed}</td><td>{summary.buffer_levels[asset.input_buffer]} / {profile.scene.zones.find(z => z.id === asset.input_buffer)?.capacity ?? t("uncapped")}<small>{asset.input_buffer}</small></td><td>{asset.output_buffer === "finished" ? summary.finished_goods_available : summary.buffer_levels[asset.output_buffer]}<small>{asset.output_buffer}</small></td></tr>)}</tbody></table></div></section>
    <OrderBoard session={session} busy={!!control.busy} save={control.prioritize}/>
  </div>;
}
