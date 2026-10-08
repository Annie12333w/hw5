import type { PaymentRequest, Ticket } from "../types";

const TYPE_LABEL: Record<string, string> = {
  customer_order: "Customer order",
  rent_notice: "Rent notice",
  price_override: "Price override",
};

export const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  in_progress: "In progress",
  waiting_approval: "Needs approval",
  blocked: "Blocked",
  resolved: "Resolved",
};

interface Props {
  tickets: Ticket[];
  selected: number | null;
  runningTicket: number | null;
  pending: PaymentRequest[];
  onSelect: (id: number) => void;
  onRun: (id: number) => void;
  onReset: () => void;
  limitReached: boolean;
}

function detail(t: Ticket): string {
  if (t.sku) return `${t.qty ?? "?"} × ${t.sku} · size ${t.size ?? "-"}`;
  if (t.lease_id) return `Lease #${t.lease_id}`;
  if (t.invoice_id) return `Invoice #${t.invoice_id}`;
  return "";
}

export function TicketList({ tickets, selected, runningTicket, pending, onSelect, onRun, onReset, limitReached }: Props) {
  return (
    <aside className="tickets" aria-label="Tickets">
      <div className="col-head">
        <h2>Tickets</h2>
        <span className="muted">{tickets.filter((t) => t.is_open).length} open</span>
      </div>

      <ul className="ticket-list">
        {tickets.map((t) => {
          const isSel = t.id === selected;
          const isRunning = runningTicket === t.id;
          const waiting = pending.filter((p) => p.ticket_id === t.id).length;
          return (
            <li key={t.id}>
              <div
                role="button"
                tabIndex={0}
                className={`ticket ${isSel ? "selected" : ""} ${t.is_open ? "" : "closed"} ${isRunning ? "running" : ""}`}
                onClick={() => onSelect(t.id)}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(t.id)}
                aria-pressed={isSel}
              >
                <div className="ticket-top">
                  <span className="ticket-id">#{t.id}</span>
                  <span className={`badge status-${t.status}`}>{STATUS_LABEL[t.status] ?? t.status}</span>
                </div>
                <div className="ticket-subject">{t.subject}</div>
                <div className="ticket-meta">{TYPE_LABEL[t.type] ?? t.type} · {t.requester}</div>
                <div className="ticket-meta mono">{detail(t)}</div>
                {waiting > 0 && <div className="ticket-flag">💳 {waiting} payment{waiting > 1 ? "s" : ""} awaiting you</div>}
                {isRunning && <div className="ticket-flag live"><span className="pulse-dot" /> Agents working…</div>}

                {isSel && (
                  <button
                    className="btn primary block"
                    disabled={runningTicket !== null || !t.is_open || limitReached}
                    onClick={(e) => { e.stopPropagation(); onRun(t.id); }}
                    title={!t.is_open ? "Ticket is resolved" : runningTicket !== null ? `Ticket #${runningTicket} is running`
                      : limitReached ? "Spend limit reached: raise it in the top bar or reset the shop data" : ""}
                  >
                    {isRunning ? "Running…" : limitReached ? "Spend limit reached" : "▶ Run agent team"}
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      <div className="col-foot">
        <button className="btn ghost block" onClick={onReset} disabled={runningTicket !== null}
                title="Restore campus_customs_new.db from the original for a fresh run">
          ↺ Reset shop data
        </button>
        <p className="tiny muted">Copies the original campus_customs.db over the working copy. The audit trail is kept.</p>
      </div>
    </aside>
  );
}
