import type { AssetConfig, MachineMetric } from "../types";
import type { PlantSession } from "../hooks/usePlantSession";
import { money } from "../format";

export function MachineActions({asset, metric, control}: {asset: AssetConfig; metric: MachineMetric; control: PlantSession}) {
  const closed = !!control.session && control.session.summary.simulated_minutes >= control.session.summary.shift_minutes;
  const service = metric.service;
  const allowed = !closed && !service?.pending && !service?.active && ["IDLE", "STARVED", "BLOCKED"].includes(metric.state) && asset.maintenance_available;
  const reason = closed ? "Shift closed; maintenance decisions are locked." : !asset.maintenance_available ? asset.maintenance_unavailable_reason : allowed
    ? `${asset.maintenance_duration} min planned stop; restores health to 100. Cycle capacity and lot reject risk stay unchanged.`
    : `Preventive maintenance cannot start while ${metric.state.toLowerCase().replace(/_/g, " ")}.`;
  if (asset.stage_role === "quality") return <p>Manage intensified inspection in the Quality workspace. Release capacity and containment workload are tracked there.</p>;
  if (service) return <div className="machine-actions">
    <button disabled={!!control.busy || !!service.unavailable_reason} onClick={() => void control.service(asset.id, service.action)}>{service.label} · {money(service.cost)}</button>
    <small>{service.unavailable_reason ?? `${service.duration} min planned stop. Completes the current unit first; restores the underlying condition.`}</small>
    <small>{service.pending ? "Queued at the next cycle boundary." : service.active ? "Service in progress; resume playback to complete." : !service.unavailable_reason ? "Available during control hold; time advances only on playback." : null}</small>
  </div>;
  return <div className="machine-actions"><button disabled={closed || !!control.busy || metric.state !== "DOWN"} onClick={() => void control.repair(asset.id)}>Call emergency repair · 350.00</button><small>{metric.state === "DOWN" ? "Immediate repair. Ordinary repair is cancelled." : "Emergency repair requires an unplanned failure."}</small>
    {asset.maintenance_available && <button disabled={!!control.busy || !allowed} onClick={() => void control.maintain(asset.id)}>{asset.maintenance_label} · {money(asset.maintenance_cost)}</button>}<small>{reason}</small>
  </div>;
}
