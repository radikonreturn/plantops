import type { AssetConfig, MachineMetric } from "../types";
import type { PlantSession } from "../hooks/usePlantSession";
import { money } from "../format";

export function MachineActions({asset, metric, control}: {asset: AssetConfig; metric: MachineMetric; control: PlantSession}) {
  const allowed = ["IDLE", "STARVED", "BLOCKED"].includes(metric.state) && asset.maintenance_duration > 0;
  const reason = asset.maintenance_duration <= 0 ? "No preventive plan configured for this asset." : allowed
    ? `${asset.maintenance_duration} min planned stop; restores health to 100.`
    : `Preventive maintenance cannot start while ${metric.state.toLowerCase().replace(/_/g, " ")}.`;
  return <div className="machine-actions"><button disabled={!!control.busy || metric.state !== "DOWN"} onClick={() => void control.repair(asset.id)}>Call emergency repair · 350.00</button><small>{metric.state === "DOWN" ? "Immediate repair. Ordinary repair is cancelled." : "Emergency repair requires an unplanned failure."}</small>
    <button disabled={!!control.busy || !allowed} onClick={() => void control.maintain(asset.id)}>Start preventive maintenance · {money(asset.maintenance_cost)}</button><small>{reason}</small>
  </div>;
}
