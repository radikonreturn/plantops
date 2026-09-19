import { useState } from "react";
import { useI18n } from "../i18n";
import { clock } from "../format";
import type { CustomerOrder, SessionSnapshot } from "../types";
function PriorityControl({order, busy, save}: {order: CustomerOrder; busy: boolean; save: (id: string, priority: number) => Promise<boolean>}) {
  const { t } = useI18n();
  const [draft, setDraft] = useState(String(order.priority));
  const eligible = (order.status === "ACTIVE" || order.status === "LATE") && order.remaining_quantity > 0;
  return <form className="priority-control" onSubmit={event => {event.preventDefault(); void save(order.id, Number(draft));}}>
    <input aria-label={t("Priority for {value1}", {value1: order.id})} type="number" min="0" max="100" step="1" required value={draft} onChange={e => setDraft(e.target.value)} disabled={busy || !eligible} title={!eligible ? t("Only released, unfinished orders can change priority") : t("Priority breaks ties between equal due dates")} />
    <button type="submit" disabled={busy || !eligible || draft === "" || Number(draft) === order.priority}>{t("Save")}</button>
    <button type="button" disabled={busy || !eligible || order.priority >= 100} onClick={() => void save(order.id, Math.min(100, order.priority + 10))}>{t("Rush")}</button>
  </form>;
}
export function OrderBoard({session, busy, save}: {session: SessionSnapshot; busy: boolean; save: (id: string, priority: number) => Promise<boolean>}) {
  const { t, label, percent } = useI18n();
  const orders = session.summary.order_summary;
  return <section className="order-board"><div className="section-heading"><h2>{t("Customer commitments")}</h2><span>{t("{value1} delivered · {value2} backlog · OTIF {value3}", {value1: orders.units_delivered, value2: orders.backlog_units, value3: percent(orders.otif)})}</span></div>
    <div className="commitment-chart" aria-label={t("Order release and due windows against shift clock")}><p>{t("Due windows · now {value1} · shift close {value2}", {value1: clock(session.summary.simulated_minutes), value2: clock(session.summary.shift_minutes)})}</p>{orders.orders.map(order => <div className="commitment-row" key={order.id}><span>{order.id}</span><div className="commitment-track"><span className="commitment-window" style={{left: `${order.release_minute / session.summary.shift_minutes * 100}%`, width: `${(order.due_minute - order.release_minute) / session.summary.shift_minutes * 100}%`}}/><i style={{left: `${session.summary.simulated_minutes / session.summary.shift_minutes * 100}%`}}/></div><span>{t("{value1} due", {value1: clock(order.due_minute)})}</span></div>)}</div>
    <div className="table-scroll"><table><thead><tr><th>{t("Order / release")}</th><th>{t("Qty")}</th><th>{t("Fulfilled")}</th><th>{t("Remaining")}</th><th>{t("Due")}</th><th>{t("Status / risk")}</th><th>{t("Priority decision")}</th></tr></thead><tbody>{orders.orders.map(order => <tr key={order.id} className={order.status === "LATE" ? "late-row" : ""}>
      <td><strong>{order.id}</strong>{order.id.includes("URGENT") && <span className="tag attention">{t("Urgent")}</span>}<small>{t("Release {value1}", {value1: clock(order.release_minute)})}</small></td><td>{order.quantity}</td><td>{order.fulfilled_quantity}</td><td><strong>{order.remaining_quantity}</strong></td><td>{clock(order.due_minute)}<small>{t("M{value1}", {value1: order.due_minute})}</small></td><td><span className={`state-tag ${order.status === "LATE" || order.status === "COMPLETED_LATE" ? "critical" : ""}`}>{label(order.status)}</span><small>{session.scenario_profile.scene.order_risks[order.id]}</small>{session.scenario_profile.scene.order_forecasts[order.id] != null && <small>{t("Optimistic forecast {value1}", {value1: clock(session.scenario_profile.scene.order_forecasts[order.id]!)})}</small>}</td><td><PriorityControl key={`${order.id}-${order.priority}`} order={order} busy={busy || session.summary.simulated_minutes >= session.summary.shift_minutes} save={save} /></td>
    </tr>)}</tbody></table></div><p className="table-note">{t("Allocation: earliest due → higher priority → order ID. Raising one priority can delay another with the same deadline. Forecast uses remaining demand in allocation order × bottleneck cycle from now; excludes losses, pipeline transit and inbound waits. It is not a delivery promise. Only released unfinished orders can change priority; shift close locks decisions.")}</p>
  </section>;
}
