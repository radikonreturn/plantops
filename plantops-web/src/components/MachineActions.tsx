import { useI18n } from "../i18n";
import type { AssetConfig, MachineMetric } from "../types";
import type { PlantSession } from "../hooks/usePlantSession";

export function MachineActions({asset, metric, control}: {asset: AssetConfig; metric: MachineMetric; control: PlantSession}) {
  const { t, money, label } = useI18n();
  const closed = !!control.session && control.session.summary.simulated_minutes >= control.session.summary.shift_minutes;
  const service = metric.service;
  const allowed = !closed && !service?.pending && !service?.active && ["IDLE", "STARVED", "BLOCKED"].includes(metric.state) && asset.maintenance_available;
  const reason = closed ? t("Shift closed; maintenance decisions are locked.") : !asset.maintenance_available ? asset.maintenance_unavailable_reason : allowed
    ? t("{value1} min planned stop; restores health to 100. Cycle capacity and lot reject risk stay unchanged.", {value1: asset.maintenance_duration})
    : t("Preventive maintenance cannot start while {value1}.", {value1: label(metric.state)});
  if (asset.stage_role === "quality") return <p>{t("Manage intensified inspection in the Quality workspace. Release capacity and containment workload are tracked there.")}</p>;
  if (service) return <div className="machine-actions">
    <button data-action={service.action} disabled={!!control.busy || !!service.unavailable_reason} onClick={() => void control.service(asset.id, service.action)}>{service.label} · {money(service.cost)}</button>
    <small>{service.unavailable_reason ?? t("{value1} min planned stop. Completes the current unit first; restores the underlying condition.", {value1: service.duration})}</small>
    <small>{service.pending ? t("Queued at the next cycle boundary.") : service.active ? t("Service in progress; resume playback to complete.") : !service.unavailable_reason ? t("Available during control hold; time advances only on playback.") : null}</small>
  </div>;
  return <div className="machine-actions"><button disabled={closed || !!control.busy || metric.state !== "DOWN"} onClick={() => void control.repair(asset.id)}>{t("Call emergency repair · 350.00")}</button><small>{metric.state === "DOWN" ? t("Immediate repair. Ordinary repair is cancelled.") : t("Emergency repair requires an unplanned failure.")}</small>
    {asset.maintenance_available && <button disabled={!!control.busy || !allowed} onClick={() => void control.maintain(asset.id)}>{asset.maintenance_label} · {money(asset.maintenance_cost)}</button>}<small>{reason}</small>
  </div>;
}
