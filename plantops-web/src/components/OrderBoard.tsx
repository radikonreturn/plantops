import type { CustomerOrder, OrderSummary } from "../types";

interface OrderBoardProps {
  orderSummary: OrderSummary;
  simulatedMinutes: number;
  busy: boolean;
  onRushOrder: (order: CustomerOrder) => void;
}

function statusLabel(status: CustomerOrder["status"]): string {
  return status.replace(/_/g, " ");
}

function dueLabel(order: CustomerOrder, simulatedMinutes: number): string {
  if (order.status.startsWith("COMPLETED")) return `M${order.due_minute}`;
  const delta = order.due_minute - simulatedMinutes;
  if (delta < 0) return `${Math.abs(Math.round(delta))}m overdue`;
  return `${Math.round(delta)}m remaining`;
}

export function OrderBoard({
  orderSummary,
  simulatedMinutes,
  busy,
  onRushOrder,
}: OrderBoardProps) {
  return (
    <section className="order-board panel-frame" aria-labelledby="order-board-title">
      <div className="section-heading order-board__heading">
        <div>
          <span className="section-code">CUSTOMER COMMITMENTS / EDF DISPATCH</span>
          <h2 id="order-board-title">Order board</h2>
        </div>
        <div className="order-board__totals">
          <span><b>{orderSummary.orders_completed}</b> completed</span>
          <span><b>{orderSummary.backlog_orders}</b> open backlog</span>
          <span><b>{orderSummary.orders_late}</b> late</span>
        </div>
      </div>

      <div className="table-scroll">
        <table className="operations-table">
          <thead>
            <tr>
              <th>Order</th>
              <th className="numeric">Qty</th>
              <th className="numeric">Fulfilled</th>
              <th className="numeric">Remaining</th>
              <th>Due</th>
              <th className="numeric">Priority</th>
              <th>Status</th>
              <th><span className="visually-hidden">Action</span></th>
            </tr>
          </thead>
          <tbody>
            {orderSummary.orders.map((order) => {
              const urgent = order.id.includes("URGENT");
              const eligible =
                (order.status === "ACTIVE" || order.status === "LATE") &&
                order.remaining_quantity > 0 &&
                order.priority < 100;
              return (
                <tr
                  key={order.id}
                  className={`${urgent ? "is-urgent" : ""} ${order.status === "LATE" ? "is-late" : ""}`}
                >
                  <td>
                    <strong>{order.id}</strong>
                    {urgent ? <span className="urgent-flag">URGENT</span> : null}
                  </td>
                  <td className="numeric">{order.quantity}</td>
                  <td className="numeric">{order.fulfilled_quantity}</td>
                  <td className="numeric emphasis">{order.remaining_quantity}</td>
                  <td>
                    <strong>M{order.due_minute}</strong>
                    <small>{dueLabel(order, simulatedMinutes)}</small>
                  </td>
                  <td className="numeric priority-cell">P{order.priority}</td>
                  <td>
                    <span className={`order-status order-status--${order.status.toLowerCase()}`}>
                      {statusLabel(order.status)}
                    </span>
                  </td>
                  <td className="action-cell">
                    <button
                      type="button"
                      className="table-action"
                      onClick={() => onRushOrder(order)}
                      disabled={!eligible || busy}
                      title={
                        order.priority >= 100
                          ? "Priority is already at the maximum"
                          : eligible
                            ? `Raise priority to ${Math.min(100, order.priority + 10)}`
                            : "Only released, incomplete orders can be rushed"
                      }
                    >
                      Rush +10
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="allocation-note">
        Future allocation: earliest due date → highest priority → order ID. Existing allocations stay assigned.
      </p>
    </section>
  );
}
