import { FormEvent, useState } from "react";
import type { MachineMetric, SessionSnapshot } from "../types";

interface OperationsPanelProps {
  session: SessionSnapshot;
  selectedMachineId: string;
  alert: string | null;
  busy: boolean;
  busyLabel: string | null;
  onDismissAlert: () => void;
  onExpediteRepair: (machineId: string) => void;
  onStartMaintenance: (machineId: string) => void;
  onPlacePurchaseOrder: (quantity: number) => void;
}

const displayNames: Record<string, string> = {
  cnc_01: "CNC-01",
  wash_01: "Wash-01",
  assembly_01: "Assembly-01",
  quality_01: "Quality-01",
};

function maintenanceReason(machineId: string, metric: MachineMetric): string {
  if (machineId !== "cnc_01") {
    return "Preventive maintenance is not configured for this asset in the MVP.";
  }
  if (metric.state === "RUNNING") {
    return "Stop condition unavailable: machine is processing a unit.";
  }
  if (metric.state === "DOWN") {
    return "Resolve the unplanned failure before planned maintenance.";
  }
  if (metric.state === "PLANNED_MAINTENANCE") {
    return "The preventive-maintenance plan is already active.";
  }
  return "Eligible from IDLE, STARVED, or BLOCKED state.";
}

export function OperationsPanel({
  session,
  selectedMachineId,
  alert,
  busy,
  busyLabel,
  onDismissAlert,
  onExpediteRepair,
  onStartMaintenance,
  onPlacePurchaseOrder,
}: OperationsPanelProps) {
  const [quantity, setQuantity] = useState("100");
  const metric = session.summary.machine_metrics[selectedMachineId];
  const supply = session.summary.supply_summary;
  const isCnc = selectedMachineId === "cnc_01";
  const canRepair = isCnc && metric.state === "DOWN";
  const canMaintain =
    isCnc && ["IDLE", "STARVED", "BLOCKED"].includes(metric.state);

  function submitPurchaseOrder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = Number(quantity);
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 1000) return;
    onPlacePurchaseOrder(parsed);
  }

  return (
    <aside className="operations-panel panel-frame" aria-labelledby="operations-title">
      <div className="section-heading">
        <div>
          <span className="section-code">OPERATOR ACTIONS</span>
          <h2 id="operations-title">Operations</h2>
        </div>
        {busy ? <span className="request-indicator">{busyLabel ?? "Updating"}</span> : null}
      </div>

      <div className={`operations-alert ${alert ? "is-visible" : ""}`} role="alert" aria-live="polite">
        <span className="alert-marker" aria-hidden="true">!</span>
        <p>{alert ?? "No active API or network alerts."}</p>
        {alert ? (
          <button type="button" onClick={onDismissAlert} aria-label="Dismiss alert">×</button>
        ) : null}
      </div>

      <section className="ops-section selected-asset">
        <div className="ops-section__title">
          <span>SELECTED ASSET</span>
          <strong>{displayNames[selectedMachineId] ?? selectedMachineId}</strong>
        </div>
        <div className="asset-detail-grid">
          <span>State<b className={`text-state text-state--${metric.state.toLowerCase()}`}>{metric.state.replace(/_/g, " ")}</b></span>
          <span>Health<b>{metric.health.toFixed(1)} / 100</b></span>
          <span>Unplanned down<b>{metric.unplanned_downtime_minutes.toFixed(1)} min</b></span>
          <span>PM count<b>{metric.maintenance_count}</b></span>
        </div>
        <div className="action-stack">
          {canRepair ? (
            <button
              type="button"
              className="action-button action-button--danger"
              disabled={busy}
              onClick={() => onExpediteRepair("CNC-01")}
            >
              <span>Call emergency repair</span>
              <strong>350.00</strong>
            </button>
          ) : (
            <div className="action-unavailable">
              <strong>Emergency repair unavailable</strong>
              <span>{isCnc ? "CNC-01 is not currently DOWN." : "Emergency call-out is shown for the CNC failure point."}</span>
            </div>
          )}

          <button
            type="button"
            className="action-button action-button--maintenance"
            disabled={!canMaintain || busy}
            onClick={() => onStartMaintenance("CNC-01")}
          >
            <span>Start preventive maintenance</span>
            <strong>250.00</strong>
          </button>
          <p className="action-guidance">{maintenanceReason(selectedMachineId, metric)}</p>
        </div>
      </section>

      <section className="ops-section procurement-section">
        <div className="ops-section__title">
          <span>SUPPLY CONTROL</span>
          <strong>STEEL-01</strong>
        </div>
        <p className="supplier-name">Anatolia Steel Blanks · 18.50 / unit</p>
        <form className="purchase-form" onSubmit={submitPurchaseOrder}>
          <label htmlFor="purchase-quantity">Purchase quantity</label>
          <div>
            <input
              id="purchase-quantity"
              type="number"
              min="1"
              max="1000"
              step="1"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              disabled={busy}
            />
            <button type="submit" disabled={busy || !quantity}>
              Place purchase order
            </button>
          </div>
        </form>
        <div className="supply-readouts">
          <span>Inbound material<b>{supply.inbound_units} units</b></span>
          <span>Open POs<b>{supply.purchase_orders_open}</b></span>
          <span>Received POs<b>{supply.purchase_orders_received}</b></span>
          <span>Late POs<b>{supply.purchase_orders_late}</b></span>
          <span className="wide">Committed procurement<b>{supply.procurement_committed_cost.toFixed(2)}</b></span>
        </div>
        {supply.purchase_orders.length ? (
          <div className="po-list" aria-label="Recent purchase orders">
            {supply.purchase_orders.slice(-3).reverse().map((order) => (
              <div key={order.id}>
                <span>{order.id}</span>
                <b>{order.quantity} u</b>
                <small>{order.status.replace(/_/g, " ")}</small>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-record">No purchase orders placed this shift.</p>
        )}
      </section>

      <section className="ops-section cost-ledger">
        <div className="ops-section__title">
          <span>SHIFT COST LEDGER</span>
        </div>
        <div><span>Emergency repair</span><strong>{session.intervention_cost.toFixed(2)}</strong></div>
        <div><span>Preventive maintenance</span><strong>{session.preventive_maintenance_cost.toFixed(2)}</strong></div>
        <div><span>Procurement committed</span><strong>{supply.procurement_committed_cost.toFixed(2)}</strong></div>
      </section>
    </aside>
  );
}
