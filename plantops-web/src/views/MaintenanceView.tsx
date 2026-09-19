import { useI18n } from "../i18n";
import type { PlantSession } from "../hooks/usePlantSession";

import { MachineActions } from "../components/MachineActions";
export function MaintenanceView({control}: {control: PlantSession}) {
  const { t, label, money, percent } = useI18n();
  const session = control.session!;
  return <div className="office-view"><div className="view-heading"><h1>{t("Maintenance")}</h1><span>{t("Condition and intervention register")}</span></div>
    <p>{session.overtime?.fatigue_active ? t("Overtime fatigue: current failure probabilities include a 1.2× multiplier.") : t("No overtime fatigue modifier active.")}</p>
    {session.shift_events?.filter(e => e.state === "active" && (e.workspace === "Maintenance" || e.kind === "operator_shortage")).map(e => <p key={e.id}><strong>{e.zone}: {e.title}</strong> — {e.detail}</p>)}
    <p>{t("Condition burden is 0 at best and 100 at worst; spindle health is 100 at best. Asset service restores condition. Preventive maintenance restores health after a configured planned stop. Emergency repair ends a current unplanned failure immediately. Planning actions are available while the shift is paused.")}</p>
    <dl className="readings horizontal"><div><dt>{t("Emergency call-outs")}</dt><dd>{money(session.intervention_cost)}</dd></div><div><dt>{t("Preventive maintenance")}</dt><dd>{money(session.preventive_maintenance_cost)}</dd></div></dl>
    {session.scenario_profile.machines.map(asset => {
      const metric = session.summary.machine_metrics[asset.id];
      return <section className="maintenance-row" key={asset.id}><div><h2>{asset.name}</h2><p>{asset.fault_mode}</p>{asset.attention_reason && <p>{asset.attention_reason}</p>}<span className={`state-tag ${metric.state === "DOWN" ? "critical" : ""}`}>{label(metric.state)}</span><dl className="readings">{metric.condition_label && <><div><dt>{metric.condition_label}</dt><dd>{metric.condition_value?.toFixed(1)} / 100</dd></div><div><dt>{t("Cycle multiplier")}</dt><dd>{metric.cycle_time_multiplier?.toFixed(2)}×</dd></div><div><dt>{t("Rework / retests")}</dt><dd>{metric.rework}</dd></div></>}<div><dt>{t("Health")}</dt><dd>{metric.health.toFixed(1)} / 100</dd></div><div><dt>{t("Condition upset / unit")}</dt><dd>{percent(asset.failure_risk)}</dd></div><div><dt>{t("Failures")}</dt><dd>{metric.failures}</dd></div><div><dt>{t("Unplanned downtime")}</dt><dd>{t("{value1} min", {value1: metric.unplanned_downtime_minutes.toFixed(1)})}</dd></div><div><dt>{t("Planned maintenance")}</dt><dd>{t("{value1} min", {value1: metric.planned_maintenance_minutes.toFixed(1)})}</dd></div><div><dt>{t("Completed plans")}</dt><dd>{metric.maintenance_count}</dd></div></dl>{metric.action_history?.map((a, i) => <p key={i}>{a.action} · {money(a.cost)} · {a.completed_minute !== null ? t("Completed at {value1} min", {value1: a.completed_minute.toFixed(1)}) : a.started_minute !== null ? t("In progress") : t("Queued")}</p>)}</div><MachineActions asset={asset} metric={metric} control={control}/></section>;
    })}
    <section className="work-section"><h2>{t("Repair and service history")}</h2>{session.maintenance_history.map(a => <p key={a.id}>{t("Minute {value1} · {value2} · {value3} · {value4}", {value1: a.minute.toFixed(1), value2: a.machine_id, value3: label(a.kind), value4: a.detail || (a.kind === "REPAIR_EXPEDITED" ? t("350 call-out cost") : "")})}</p>)}</section>
    <p className="table-note">{t("Availability excludes planned-maintenance time from planned production time. Failure downtime reduces availability.")}</p>
  </div>;
}
