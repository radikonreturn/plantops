import type { AssetConfig, MachineMetric } from "../types";
import type { PlantSession } from "../hooks/usePlantSession";
import { money } from "../format";

export function MachineActions({asset, metric, control}: {asset: AssetConfig; metric: MachineMetric; control: PlantSession}) {
  const allowed = ["IDLE", "STARVED", "BLOCKED"].includes(metric.state) && asset.maintenance_available;
  const reason = !asset.maintenance_available ? asset.maintenance_unavailable_reason : allowed
    ? `${asset.maintenance_duration} min planned stop; restores health to 100. Cycle capacity and lot reject risk stay unchanged.`
    : `Preventive maintenance cannot start while ${metric.state.toLowerCase().replace(/_/g, " ")}.`;
  return <div className="machine-actions"><button disabled={!!control.busy || metric.state !== "DOWN"} onClick={() => void control.repair(asset.id)}>Call emergency repair · 350.00</button><small>{metric.state === "DOWN" ? "Immediate repair. Ordinary repair is cancelled." : "Emergency repair requires an unplanned failure."}</small>
    {asset.maintenance_available && <button disabled={!!control.busy || !allowed} onClick={() => void control.maintain(asset.id)}>{asset.maintenance_label} · {money(asset.maintenance_cost)}</button>}<small>{reason}</small>
  </div>;
}
