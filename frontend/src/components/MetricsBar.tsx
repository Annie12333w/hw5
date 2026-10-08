import { useState } from "react";
import { money } from "../api";
import type { Metrics } from "../types";
import { SpendBar, fmtTokens, fmtUsd } from "./SpendBar";

interface Props {
  metrics: Metrics | null;
  online: boolean;
  supervisor: string;
  onSupervisor: (name: string) => void;
  soundOn: boolean;
  onToggleSound: () => void;
  cashFlash: "down" | null;
  onSetLimit: (usd: number) => Promise<void>;
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className={`stat ${tone ?? ""}`}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}

function SpendTile({ m, onSetLimit }: { m: Metrics; onSetLimit: (usd: number) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const live = !!m.active_run_id;
  const save = async () => {
    const v = Number(draft.replace(/[$,\s]/g, ""));
    if (!(v > 0)) return;
    await onSetLimit(v);
    setEditing(false);
  };
  return (
    <div className={`stat spend-stat ${live ? "live" : ""} ${m.limit_reached ? "over" : ""}`}>
      <span className="stat-label">
        Agent spend {live && <span className="live-pill">● live</span>}
        {m.limit_reached && <span className="limit-pill">limit reached</span>}
      </span>
      <div className="spend-head">
        <span className="stat-value">{fmtUsd(m.spend_since_reset_usd)}</span>
        {!editing ? (
          <button className="limit-btn" onClick={() => { setDraft(m.spend_limit_usd.toFixed(2)); setEditing(true); }}
                  title="Set the dollar limit. The agents stop when spend since the last reset reaches it.">
            of {fmtUsd(m.spend_limit_usd)} limit ✎
          </button>
        ) : (
          <form className="limit-form" onSubmit={(e) => { e.preventDefault(); void save(); }}>
            <span>$</span>
            <input autoFocus inputMode="decimal" value={draft} onChange={(e) => setDraft(e.target.value)}
                   aria-label="Spend limit in dollars" />
            <button type="submit">Set</button>
            <button type="button" onClick={() => setEditing(false)} aria-label="Cancel">✕</button>
          </form>
        )}
      </div>
      <SpendBar usd={m.spend_since_reset_usd} limitUsd={m.spend_limit_usd} size="lg" live={live} dark />
      <span className="stat-sub" title={`Priced at $${m.price_input_per_million_usd}/1M input and $${m.price_output_per_million_usd}/1M output tokens (gpt-6-luna)`}>
        {live
          ? `This run: ${fmtUsd(m.active_run_spend_usd)} · ${fmtTokens(m.active_run_tokens)} tokens`
          : `${fmtTokens(m.tokens_since_reset)} tokens · ${m.runs_since_reset} runs since reset`}
      </span>
    </div>
  );
}

export function MetricsBar({ metrics: m, online, supervisor, onSupervisor, soundOn, onToggleSound, cashFlash, onSetLimit }: Props) {
  return (
    <header className="metrics">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">CC</span>
        <div>
          <div className="brand-name">Campus Customs</div>
          <div className="brand-sub">Agent Desk</div>
        </div>
      </div>

      <div className="stats" aria-label="Shop metrics">
        <Stat label="Shop date" value={m?.shop_date ?? "-"} sub="shop's today" />
        <Stat label="Open tickets" value={m ? String(m.open_tickets) : "-"} />
        <Stat label="Resolved" value={m ? String(m.resolved_tickets) : "-"} tone={m?.resolved_tickets ? "good" : ""} />
        <Stat
          label="Checking"
          value={money(m?.cash_balance)}
          sub={m && m.cash_pending > 0 ? `${money(m.cash_pending)} awaiting approval` : "nothing pending"}
          tone={cashFlash === "down" ? "flash" : ""}
        />
        {m && <SpendTile m={m} onSetLimit={onSetLimit} />}
      </div>

      <div className="header-tools">
        <label className="supervisor">
          <span>Supervisor</span>
          <input
            value={supervisor}
            onChange={(e) => onSupervisor(e.target.value)}
            placeholder="Supervisor #1"
            aria-label="Approver name recorded on payments (defaults to Supervisor #1)"
            title="Recorded as the approver on payments. Leave as Supervisor #1 or type your name."
          />
        </label>
        <button className="icon-btn" onClick={onToggleSound} aria-pressed={soundOn}
                title={soundOn ? "Chime on: click to mute" : "Chime muted: click to unmute"}>
          {soundOn ? "🔔" : "🔕"}
        </button>
        <span className={`conn ${online ? "on" : "off"}`} title={online ? "Backend connected" : "Backend offline"}>
          <span className="dot" /> <span className="label">{online ? "Live" : "Offline"}</span>
        </span>
      </div>
    </header>
  );
}
