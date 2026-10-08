import { useEffect, useRef, useState } from "react";
import { AGENTS, agentTitle, isAgent } from "../agents";
import type { AgentEvent, ToolUse } from "../types";

type Filter = "all" | "talk" | "tools" | "flags";

// Plain-English names for the MCP tools (the raw name is still shown inside each chip).
export const TOOL_LABEL: Record<string, string> = {
  check_stock: "checked the shelf",
  check_vendor_invoices: "checked the vendor",
  get_lease_status: "checked the lease",
  get_shop_date: "checked today's date",
  list_tickets: "reviewed the board",
  get_ticket: "read the ticket",
  get_cash_balance: "checked the bank balance",
  check_price_margin: "checked the margin",
  list_payments: "checked past payments",
  list_payment_requests: "checked pending approvals",
  update_ticket: "updated the ticket",
  save_draft: "wrote a draft",
  draft_purchase_order: "drafted a purchase order",
  request_payment: "asked you to approve a payment",
  approve_payment: "approved a payment",
  reject_payment: "rejected a payment",
  set_spend_limit: "set the spend limit",
  delegate: "handed off work",
  finish: "wrote the final report",
};
const toolLabel = (t: string) => TOOL_LABEL[t] ?? t.replace(/_/g, " ");

const time = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

function headline(e: AgentEvent): string {
  const who = agentTitle(e.agent);
  switch (e.event) {
    case "run_start": return "The team started";
    case "context_loaded": return "Opened the ticket";
    case "agent_start": return `${who} picked up a task`;
    case "llm_step":
      if (e.tools.some((t) => t.tool === "finish")) return `${who} is wrapping up`;
      if (e.tools.some((t) => t.tool === "delegate")) return `${who} is handing off work`;
      return `${who} is working`;
    case "tool_call": return `${who} ${toolLabel(e.tools[0]?.tool ?? "")}`;
    case "delegation": return e.said?.startsWith("Handed off") ? `${who} handed off work` : `${who} got a report back`;
    case "guardrail": return "A safety rule stopped something";
    case "agent_finish": return `${who} finished`;
    case "run_end": return "The team is done";
    case "human_decision": return `You ${toolLabel(e.tools[0]?.tool ?? "acted")}`;
    case "reset": return "Shop data reset";
    case "error": return "Something went wrong";
    default: return e.event;
  }
}

function matches(e: AgentEvent, f: Filter) {
  if (f === "all") return true;
  if (f === "talk") return ["llm_step", "agent_finish", "delegation", "run_end"].includes(e.event) && !!e.said;
  if (f === "tools") return e.event === "tool_call" || e.event === "context_loaded" || e.event === "human_decision";
  return e.event === "guardrail" || e.event === "error" || e.event === "human_decision";
}

function ToolChip({ t }: { t: ToolUse }) {
  const state = t.ok === null ? "asked" : t.ok ? "ok" : "fail";
  const refused = typeof t.result === "object" && t.result !== null && (t.result as { ok?: boolean }).ok === false;
  return (
    <details className={`tool tool-${refused ? "refused" : state}`}>
      <summary title="Show the exact data sent and received">
        <span className="tool-name">{toolLabel(t.tool)}</span>
        {refused && <span className="tool-tag">refused</span>}
        <span className="tool-more">details</span>
      </summary>
      <div className="tool-raw">Tool: <code>{t.tool}</code></div>
      <div className="tool-body">
        <div className="tool-label">Arguments</div>
        <pre>{JSON.stringify(t.arguments, null, 2)}</pre>
        {t.result !== null && t.result !== undefined && (
          <>
            <div className="tool-label">Result</div>
            <pre>{typeof t.result === "string" ? t.result : JSON.stringify(t.result, null, 2)}</pre>
          </>
        )}
      </div>
    </details>
  );
}

export function ActivityLog({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const [filter, setFilter] = useState<Filter>("all");
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const shown = events.filter((e) => matches(e, filter));

  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [shown.length]);

  return (
    <section className="log" aria-label="Agent activity log">
      <div className="log-head">
        <h3>Running log</h3>
        <div className="seg" role="tablist" aria-label="Filter log">
          {(["all", "talk", "tools", "flags"] as Filter[]).map((f) => (
            <button key={f} role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}>
              {{ all: "Everything", talk: "What they said", tools: "Tools", flags: "Guardrails & you" }[f]}
            </button>
          ))}
        </div>
      </div>
      <div
        className="log-body"
        ref={box}
        aria-live="polite"
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
      >
        {shown.length === 0 && (
          <p className="empty">{running ? "Waiting for the first agent step…" : "No activity yet. Pick a ticket and run the agent team."}</p>
        )}
        {shown.map((e) => {
          const Avatar = isAgent(e.agent) ? AGENTS[e.agent].Avatar : null;
          return (
            <article key={e.cursor} className={`entry ev-${e.event}`} style={{ marginLeft: `${Math.max(0, e.chain.length - 1) * 18}px` }}>
              <div className="entry-icon">
                {Avatar ? <Avatar size={30} /> : <span className="sys-icon">{e.agent === "human" ? "🧑‍💼" : "⚙️"}</span>}
              </div>
              <div className="entry-main">
                <div className="entry-head">
                  <span className="entry-title">{headline(e)}</span>
                  <time>{time(e.ts_utc)}</time>
                </div>
                {e.said && e.event !== "tool_call" && <p className="entry-said">{e.said}</p>}
                {e.tools.length > 0 && (
                  <div className="entry-tools">{e.tools.map((t, i) => <ToolChip key={i} t={t} />)}</div>
                )}
              </div>
            </article>
          );
        })}
        {running && <div className="typing"><span /><span /><span /></div>}
      </div>
    </section>
  );
}
