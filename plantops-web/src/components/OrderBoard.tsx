import { useState } from "react";
import { clock, label, percent } from "../format";
import type { CustomerOrder, SessionSnapshot } from "../types";
function PriorityControl({order, busy, save}: {order: CustomerOrder; busy: boolean; save: (id: string, priority: number) => Promise<boolean>}) {
  const [draft, setDraft] = useState(String(order.priority));
  const eligible = (order.status === "ACTIVE" || order.status === "LATE") && order.remaining_quantity > 0;
  return <form className="priority-control" onSubmit={event => {event.preventDefault(); void save(order.id, Number(draft));}}>
    <input aria-label={`Priority for ${order.id}`} type="number" min="0" max="100" step="1" required value={draft} onChange={e => setDraft(e.target.value)} disabled={busy || !eligible} title={!eligible ? "Only released, unfinished orders can change priority" : "Priority breaks ties between equal due dates"} />
    <button type="submit" disabled={busy || !eligible || draft === "" || Number(draft) === order.priority}>Save</button>
    <button type="button" disabled={busy || !eligible || order.priority >= 100} onClick={() => void save(order.id, Math.min(100, order.priority + 10))}>Rush</button>
  </form>;
}
export function OrderBoard({session, busy, save}: {session: SessionSnapshot; busy: boolean; save: (id: string, priority: number) => Promise<boolean>}) {
  const orders = session.summary.order_summary;
  return <section className="order-board"><div className="section-heading"><h2>Customer commitments</h2><span>{orders.units_delivered} delivered · {orders.backlog_units} backlog · OTIF {percent(orders.otif)}</span></div>
    <div className="commitment-chart" aria-label="Order release and due windows against shift clock"><p>Due windows · now {clock(session.summary.simulated_minutes)} · shift close {clock(session.summary.shift_minutes)}</p>{orders.orders.map(order => <div className="commitment-row" key={order.id}><span>{order.id}</span><div className="commitment-track"><span className="commitment-window" style={{left: `${order.release_minute / session.summary.shift_minutes * 100}%`, width: `${(order.due_minute - order.release_minute) / session.summary.shift_minutes * 100}%`}}/><i style={{left: `${session.summary.simulated_minutes / session.summary.shift_minutes * 100}%`}}/></div><span>{clock(order.due_minute)} due</span></div>)}</div>
    <div className="table-scroll"><table><thead><tr><th>Order / release</th><th>Qty</th><th>Fulfilled</th><th>Remaining</th><th>Due</th><th>Status / risk</th><th>Priority decision</th></tr></thead><tbody>{orders.orders.map(order => <tr key={order.id} className={order.status === "LATE" ? "late-row" : ""}>
      <td><strong>{order.id}</strong>{order.id.includes("URGENT") && <span className="tag attention">Urgent</span>}<small>Release {clock(order.release_minute)}</small></td><td>{order.quantity}</td><td>{order.fulfilled_quantity}</td><td><strong>{order.remaining_quantity}</strong></td><td>{clock(order.due_minute)}<small>M{order.due_minute}</small></td><td><span className={`state-tag ${order.status === "LATE" || order.status === "COMPLETED_LATE" ? "critical" : ""}`}>{label(order.status)}</span><small>{session.scenario_profile.scene.order_risks[order.id]}</small>{session.scenario_profile.scene.order_forecasts[order.id] != null && <small>Optimistic forecast {clock(session.scenario_profile.scene.order_forecasts[order.id]!)}</small>}</td><td><PriorityControl key={`${order.id}-${order.priority}`} order={order} busy={busy || session.summary.simulated_minutes >= session.summary.shift_minutes} save={save} /></td>
    </tr>)}</tbody></table></div><p className="table-note">Allocation: earliest due → higher priority → order ID. Raising one priority can delay another with the same deadline. Forecast uses remaining demand in allocation order × bottleneck cycle from now; excludes losses, pipeline transit and inbound waits. It is not a delivery promise. Only released unfinished orders can change priority; shift close locks decisions.</p>
  </section>;
}
