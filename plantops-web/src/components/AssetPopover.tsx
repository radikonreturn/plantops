import type { PlantSession } from "../hooks/usePlantSession";
import { label, percent } from "../format";
import { Modal } from "./Modal";
import { MachineActions } from "./MachineActions";
export function AssetPopover({machineId, control, onClose}: {machineId: string; control: PlantSession; onClose: () => void}) {
  const asset = control.session!.scenario_profile.machines.find(a => a.id === machineId)!;
  const metric = control.session!.summary.machine_metrics[machineId];
  return <Modal title={asset.name} onClose={onClose}>
    <p>{asset.fault_mode}</p>{asset.attention_reason && <p>{asset.attention_reason}</p>}
    <dl className="readings"><div><dt>State</dt><dd>{label(metric.state)}</dd></div><div><dt>Health</dt><dd>{metric.health.toFixed(1)} / 100</dd></div><div><dt>Processed</dt><dd>{metric.processed}</dd></div><div><dt>Availability</dt><dd>{percent(metric.availability)}</dd></div><div><dt>Failures</dt><dd>{metric.failures}</dd></div><div><dt>Unplanned downtime</dt><dd>{metric.unplanned_downtime_minutes.toFixed(1)} min</dd></div><div><dt>Planned maintenance</dt><dd>{metric.planned_maintenance_minutes.toFixed(1)} min</dd></div><div><dt>Failure risk per unit</dt><dd>{percent(asset.failure_risk)}</dd></div></dl>
    <MachineActions asset={asset} metric={metric} control={control}/>
    <p role={control.error ? "alert" : "status"} className={control.error ? "error-text" : "muted"}>{control.error ?? control.busy ?? control.notice}</p>
  </Modal>;
}
