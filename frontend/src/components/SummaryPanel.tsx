import { useState } from "react";
import { money } from "../api";
import { AGENTS, SPECIALISTS } from "../agents";
import type { RunView } from "../runView";
import type { Draft, PaymentRequest, Ticket, TicketDetail } from "../types";

interface Props {
  ticket: Ticket;
  view: RunView;
  detail: TicketDetail | null;
  pending: PaymentRequest[];
  cash: number | null;
  supervisor: string;
  busy: boolean;
  onApprove: (req: PaymentRequest) => void;
  onReject: (req: PaymentRequest, reason: string) => void;
  onResolve: (note: string) => void;
  onRerun: () => void;
}

const KIND_LABEL: Record<PaymentRequest["kind"], string> = {
  invoice: "Vendor invoice",
  rent: "Rent",
  purchase_order: "Purchase order",
};

function PaymentCard({ req, cash, supervisor, busy, onApprove, onReject }: {
  req: PaymentRequest; cash: number | null; supervisor: string; busy: boolean;
  onApprove: (r: PaymentRequest) => void; onReject: (r: PaymentRequest, reason: string) => void;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const after = cash == null ? null : cash - req.amount;
  const short = after != null && after < 0;
  return (
    <div className={`pay-card ${short ? "short" : ""}`}>
      <div className="pay-top">
        <span className="pay-kind">{KIND_LABEL[req.kind]} #{req.ref_id}</span>
        <span className="pay-amount">{money(req.amount)}</span>
      </div>
      <div className="pay-line">To <b>{req.payee}</b> · requested by {AGENTS[req.requested_by as keyof typeof AGENTS]?.title ?? req.requested_by}</div>
      <div className="pay-reason">“{req.reason}”</div>
      <div className="pay-impact">
        Checking {money(cash)} → <b>{money(after)}</b> after approval
        {short && <span className="warn"> · not enough cash, so the pay tool will refuse</span>}
      </div>
      {!rejecting ? (
        <div className="btn-row">
          <button className="btn approve" disabled={busy} onClick={() => onApprove(req)}
                  title={`Pay now; recorded as approved by ${supervisor}`}>
            ✓ Approve {money(req.amount)}
          </button>
          <button className="btn ghost" disabled={busy} onClick={() => setRejecting(true)}>✕ Reject…</button>
        </div>
      ) : (
        <form className="btn-row" onSubmit={(e) => { e.preventDefault(); onReject(req, reason); }}>
          <input className="grow" autoFocus value={reason} onChange={(e) => setReason(e.target.value)}
                 placeholder="Reason (e.g. pay next week)" />
          <button className="btn danger" disabled={busy || !reason.trim()}>Reject</button>
          <button type="button" className="btn ghost" onClick={() => setRejecting(false)}>Cancel</button>
        </form>
      )}
    </div>
  );
}

function DraftCard({ d }: { d: Draft }) {
  const isPO = d.kind === "purchase_order";
  return (
    <details className="draft">
      <summary>
        <span className="badge draft-badge">{isPO ? "PO draft" : "Draft, not sent"}</span>
        <b>{isPO ? `${d.qty} × ${d.sku} (${d.size})` : d.subject}</b>
        <span className="muted"> → {d.recipient}</span>
      </summary>
      {isPO ? (
        <div className="draft-body">
          {d.qty} × {money(d.unit_cost)} = <b>{money(d.total)}</b> · arrives {d.expected_arrival_if_ordered_today} if ordered today ·{" "}
          {d.vendor_will_ship ? "vendor will ship" : <span className="warn">vendor blocked by an open invoice</span>}
        </div>
      ) : (
        <pre className="draft-body">{d.body}</pre>
      )}
      <div className="tiny muted">Written by {AGENTS[d.author_agent as keyof typeof AGENTS]?.title ?? d.author_agent}. Copy it to send; agents never send messages.</div>
    </details>
  );
}

export function SummaryPanel({ ticket, view, detail, pending, cash, supervisor, busy, onApprove, onReject, onResolve, onRerun }: Props) {
  const [note, setNote] = useState("");
  const boss = view.agents.boss;
  const worked = SPECIALISTS.filter((s) => view.agents[s].state !== "idle");
  const skipped = SPECIALISTS.filter((s) => view.agents[s].state === "idle");
  const drafts = detail?.drafts ?? [];
  // Requests a human already approved (paid) on this ticket, shown where the request used to be.
  const approved = (detail?.payment_requests ?? []).filter((r) => r.status === "paid");
  const canResolve = ticket.is_open && pending.length === 0;

  return (
    <section className="summary" aria-label="Run summary and your actions">
      <div className="summary-grid">
        <div className="summary-col">
          <h3>What the team did</h3>
          {view.stoppedReason && (
            <div className="stopped-banner">
              <span>⚠️ This run was stopped early by a safety limit: {view.stoppedReason}. Its work may be incomplete.</span>
              <button className="btn ghost" disabled={busy || !ticket.is_open} onClick={onRerun}>↻ Run again</button>
            </div>
          )}
          {view.finalSummary && (
            <div className="final">
              <AGENTS.boss.Avatar size={40} />
              <div><div className="final-label">Boss's final call</div><p>{view.finalSummary}</p></div>
            </div>
          )}
          <ul className="who-did">
            {worked.map((s) => {
              const A = AGENTS[s].Avatar;
              const a = view.agents[s];
              return (
                <li key={s}>
                  <A size={30} />
                  <div>
                    <b>{AGENTS[s].title}</b>
                    <span className="muted"> · {a.toolsUsed.length} tool call{a.toolsUsed.length === 1 ? "" : "s"}</span>
                    <p>{a.summaries[a.summaries.length - 1] ?? "No report."}</p>
                  </div>
                </li>
              );
            })}
          </ul>
          {skipped.length > 0 && (
            <p className="tiny muted">Not needed on this ticket: {skipped.map((s) => AGENTS[s].title).join(", ")}.</p>
          )}
          {boss.summaries.length === 0 && !view.finalSummary && <p className="muted">The summary appears when the run finishes.</p>}
        </div>

        <div className="summary-col actions">
          <h3>Your move {pending.length > 0 && <span className="badge status-waiting_approval">{pending.length} waiting</span>}</h3>
          {approved.map((r) => (
            <div key={r.id} className="paid-card" role="status">
              <div className="pay-top">
                <span className="paid-title">✓ You approved a payment of {money(r.amount)}</span>
              </div>
              <div className="pay-line">
                {KIND_LABEL[r.kind]} #{r.ref_id} to <b>{r.payee}</b>
                {r.payment_id != null && <> · payment #{r.payment_id}</>}
              </div>
              <div className="tiny muted">
                Approved by {r.decided_by ?? supervisor}
                {r.decided_at_utc && <> on {new Date(r.decided_at_utc).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</>}
                . Cash has been paid out and the shop records are updated.
              </div>
            </div>
          ))}
          {pending.map((r) => (
            <PaymentCard key={r.id} req={r} cash={cash} supervisor={supervisor} busy={busy} onApprove={onApprove} onReject={onReject} />
          ))}
          {drafts.length > 0 && (
            <div className="drafts">
              <div className="sub-head">Drafts to review ({drafts.length})</div>
              {drafts.map((d) => <DraftCard key={d.id} d={d} />)}
            </div>
          )}
          <div className="resolve">
            <input className="grow" value={note} onChange={(e) => setNote(e.target.value)}
                   placeholder="Closing note (optional)" disabled={!ticket.is_open} />
            <div className="btn-row">
              <button className="btn primary" disabled={busy || !canResolve} onClick={() => onResolve(note)}
                      title={!ticket.is_open ? "Already resolved" : pending.length ? "Approve or reject the pending payment first" : "Close this ticket"}>
                {ticket.is_open ? "✓ Mark resolved" : "Resolved"}
              </button>
              <button className="btn ghost" disabled={busy || !ticket.is_open} onClick={onRerun}>↻ Run again</button>
            </div>
            {pending.length > 0 && <p className="tiny muted">Resolve unlocks after you approve or reject the pending payment.</p>}
          </div>
        </div>
      </div>
    </section>
  );
}
