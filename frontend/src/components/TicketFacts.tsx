// The summary box under the ticket title: the ticket's key facts, all read from the database
// through GET /tickets/{id} (which follows the ticket's links to inventory, pricing, invoice and lease).
import { money } from "../api";
import type { PaymentRequest, Ticket, TicketDetail } from "../types";

const TYPE_LABEL: Record<string, string> = {
  customer_order: "Customer order",
  rent_notice: "Rent notice",
  price_override: "Price override / discount",
};

const daysBetween = (from: string, to: string) =>
  Math.round((new Date(to + "T00:00:00").getTime() - new Date(from + "T00:00:00").getTime()) / 86_400_000);

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="fact-label">{label}</div>
      <div className="fact-value">{children}</div>
    </div>
  );
}

export function TicketFacts({ ticket, detail, pending }: { ticket: Ticket; detail: TicketDetail | null; pending: PaymentRequest[] }) {
  const today = detail?.date_today;
  const row = detail?.inventory?.[0];
  const onHand = detail?.inventory?.reduce((n, r) => n + r.qty, 0);
  const short = ticket.qty != null && onHand != null ? Math.max(0, ticket.qty - onHand) : null;
  const inv = detail?.invoice;
  const lease = detail?.lease;
  const drafts = detail?.drafts ?? [];
  const opened = new Date(ticket.created_at);

  return (
    <section className="facts-box" aria-label="Ticket summary">
      <div className="facts-grid">
        <Fact label="Request">
          {TYPE_LABEL[ticket.type] ?? ticket.type} from <b>{ticket.requester}</b>
          <div className="tiny muted">Opened {opened.toLocaleDateString(undefined, { month: "short", day: "numeric" })}, {opened.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</div>
        </Fact>

        {ticket.sku && (
          <Fact label="Item & stock">
            {ticket.qty} × {row?.name ?? ticket.sku}{ticket.size ? `, size ${ticket.size}` : ""}
            <div className="tiny">
              {onHand == null ? "Loading stock…" : (
                <>
                  {onHand} on hand{row?.location ? ` (${row.location})` : ""} ·{" "}
                  {short ? <span className="bad">{short} short</span> : <span className="good-text">can fill</span>}
                </>
              )}
            </div>
            {(detail?.incoming ?? []).map((i) => (
              <div key={i.id} className="tiny incoming">
                🚚 Incoming: {i.qty ?? "reprint (qty not recorded)"} from {i.vendor}, expected {i.expected_arrival}
              </div>
            ))}
          </Fact>
        )}

        {detail?.pricing && (
          <Fact label="Pricing">
            List {money(detail.pricing.list_price)} · cost {money(detail.pricing.unit_cost)}
            <div className="tiny muted">
              {Math.round(((detail.pricing.list_price - detail.pricing.unit_cost) / detail.pricing.list_price) * 100)}% margin at list; never below cost
            </div>
          </Fact>
        )}

        {inv && (
          <Fact label={`Linked invoice #${inv.id}`}>
            {money(inv.amount)} to {detail?.invoice_vendor?.name ?? `vendor #${inv.vendor_id}`} ·{" "}
            {inv.status === "open" ? <span className="bad">unpaid</span> : <span className="good-text">{inv.status}</span>}
            <div className="tiny">
              Due {inv.due_date}
              {inv.status === "open" && today && daysBetween(inv.due_date, today) > 0 && (
                <span className="bad"> · {daysBetween(inv.due_date, today)} days overdue</span>
              )}
              {detail?.invoice_vendor && <span className="muted"> · {detail.invoice_vendor.lead_days}-day lead time</span>}
            </div>
          </Fact>
        )}

        {lease && (
          <Fact label={`Lease #${lease.id}`}>
            {money(lease.monthly_rent)} rent to {lease.landlord}
            <div className="tiny">
              {lease.space_name} · due {lease.next_due}
              {today && <span className={daysBetween(today, lease.next_due) <= 3 ? "warn" : "muted"}> · in {daysBetween(today, lease.next_due)} days</span>}
            </div>
          </Fact>
        )}

        <Fact label="Waiting on you">
          {pending.length === 0 && drafts.length === 0 ? <span className="muted">Nothing yet</span> : (
            <>
              {pending.map((p) => <div key={p.id}>💳 Approve {money(p.amount)} to {p.payee} (#{p.id})</div>)}
              {drafts.length > 0 && <div>✉️ {drafts.length} draft{drafts.length > 1 ? "s" : ""} to review</div>}
            </>
          )}
        </Fact>
      </div>
      {ticket.notes && <div className="facts-note">“{ticket.notes.split("\n")[0]}”</div>}
    </section>
  );
}
