import type { PlantSession } from "../hooks/usePlantSession";
import { label, money, percent } from "../format";
import { MachineActions } from "../components/MachineActions";
export function MaintenanceView({control}: {control: PlantSession}) {
  const session = control.session!;
  return <div className="office-view"><div className="view-heading"><h1>Maintenance</h1><span>Condition and intervention register</span></div>
    <p>{session.overtime?.fatigue_active ? "Overtime fatigue: current failure probabilities include a 1.2× multiplier." : "No overtime fatigue modifier active."}</p>
    {session.shift_events?.filter(e => e.state === "active" && (e.workspace === "Maintenance" || e.kind === "operator_shortage")).map(e => <p key={e.id}><strong>{e.zone}: {e.title}</strong> — {e.detail}</p>)}
    <p>Preventive maintenance restores health after a configured planned stop. Emergency repair ends a current unplanned failure immediately. Planning actions are available while the shift is paused.</p>
    <dl className="readings horizontal"><div><dt>Emergency call-outs</dt><dd>{money(session.intervention_cost)}</dd></div><div><dt>Preventive maintenance</dt><dd>{money(session.preventive_maintenance_cost)}</dd></div></dl>
    {session.scenario_profile.machines.map(asset => {
      const metric = session.summary.machine_metrics[asset.id];
      return <section className="maintenance-row" key={asset.id}><div><h2>{asset.name}</h2><p>{asset.fault_mode}</p>{asset.attention_reason && <p>{asset.attention_reason}</p>}<span className={`state-tag ${metric.state === "DOWN" ? "critical" : ""}`}>{label(metric.state)}</span><dl className="readings"><div><dt>Health</dt><dd>{metric.health.toFixed(1)} / 100</dd></div><div><dt>Failure risk / unit</dt><dd>{percent(asset.failure_risk)}</dd></div><div><dt>Failures</dt><dd>{metric.failures}</dd></div><div><dt>Unplanned downtime</dt><dd>{metric.unplanned_downtime_minutes.toFixed(1)} min</dd></div><div><dt>Planned maintenance</dt><dd>{metric.planned_maintenance_minutes.toFixed(1)} min</dd></div><div><dt>Completed plans</dt><dd>{metric.maintenance_count}</dd></div></dl></div><MachineActions asset={asset} metric={metric} control={control}/></section>;
    })}
    <section className="work-section"><h2>Repair and service history</h2>{session.maintenance_history.map(a => <p key={a.id}>Minute {a.minute.toFixed(1)} · {a.machine_id} · {label(a.kind)} · {a.detail || (a.kind === "REPAIR_EXPEDITED" ? "350 call-out cost" : "") }</p>)}</section>
    <p className="table-note">Availability excludes planned-maintenance time from planned production time. Failure downtime reduces availability.</p>
  </div>;
}
