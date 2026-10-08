import { AGENTS, SPECIALISTS, agentTitle } from "../agents";
import type { AgentState, RunView } from "../runView";
import type { AgentName } from "../types";
import { SpendBar, fmtTokens, fmtUsd } from "./SpendBar";

const STATE_LABEL: Record<AgentState, string> = {
  idle: "Not called",
  working: "Working…",
  waiting: "Waiting",
  done: "Done",
  stopped: "Stopped",
};

const X: Record<AgentName, number> = { boss: 50, inventory: 12.5, accounting: 37.5, facilities: 62.5, customer_service: 87.5 };

function AgentCard({ name, view, running, limitUsd }: { name: AgentName; view: RunView; running: boolean; limitUsd: number }) {
  const meta = AGENTS[name];
  const a = view.agents[name];
  const active = running && view.activeChain[view.activeChain.length - 1] === name;
  const state: AgentState = active ? "working" : a.state;
  const handoff = a.calledBy && a.calledBy !== "boss" && a.calledBy !== "system" ? agentTitle(a.calledBy) : null;
  return (
    <div className={`agent state-${state} ${active ? "active" : ""}`} aria-current={active ? "true" : undefined}>
      <div className="avatar-wrap">
        <meta.Avatar size={name === "boss" ? 92 : 78} />
        {state === "done" && <span className="agent-check" aria-label="done">✓</span>}
      </div>
      <div className="agent-body">
        <div className="agent-name">{meta.title}</div>
        <div className="agent-role">{meta.animal} · {meta.outfit}</div>
        <span className={`chip chip-${state}`}>
          {state === "working" && <span className="pulse-dot" />}
          {state === "waiting" && a.waitingOn ? `Waiting on ${agentTitle(a.waitingOn)}`
            : state === "idle" && !view.runId ? "Ready" : STATE_LABEL[state]}
        </span>
        {handoff && <span className="chip chip-handoff">↪ handed off by {handoff}</span>}
      </div>
      <div className="agent-spend" title={`${fmtUsd(a.costUsd)} (${a.tokens.toLocaleString()} tokens) in this run. The bar is a share of the ${fmtUsd(limitUsd)} spend limit.`}>
        <SpendBar usd={a.costUsd} limitUsd={limitUsd} live={active} />
        <span className="agent-spend-num">
          {fmtUsd(a.costUsd)} · {fmtTokens(a.tokens)} tok{a.toolsUsed.length > 0 && ` · 🔧 ${a.toolsUsed.length}`}
        </span>
      </div>
    </div>
  );
}

export function AgentStage({ view, running, limitUsd }: { view: RunView; running: boolean; limitUsd: number }) {
  const usedEdge = (to: AgentName) => view.delegations.some((d) => d.from === "boss" && d.to === to);
  const liveEdge = (to: AgentName) => {
    const c = view.activeChain;
    const i = c.indexOf(to);
    return running && i > 0 && c[i - 1] === "boss";
  };
  return (
    <section className="stage" aria-label="Agent team">
      <div className="stage-boss">
        <AgentCard name="boss" view={view} running={running} limitUsd={limitUsd} />
      </div>

      <svg className="stage-lines" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
        {SPECIALISTS.map((s) => (
          <path
            key={s}
            d={`M50 0 C50 15, ${X[s]} 12, ${X[s]} 30`}
            className={`edge ${usedEdge(s) ? "used" : ""} ${liveEdge(s) ? "live" : ""}`}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>

      <div className="stage-row">
        {SPECIALISTS.map((s) => <AgentCard key={s} name={s} view={view} running={running} limitUsd={limitUsd} />)}
      </div>

      <div className="run-spend">
        <SpendBar usd={view.costUsd} limitUsd={limitUsd} label="This run's spend (vs. your limit)" live={running} />
      </div>

      <div className="trail" aria-label="Delegations in this run">
        <span className="trail-label">Delegations</span>
        {view.delegations.length === 0 && <span className="muted">None yet: the Boss starts every run.</span>}
        {view.delegations.map((d, i) => (
          <span key={d.cursor} className="trail-step">
            {i > 0 && <span className="trail-sep">·</span>}
            <b>{agentTitle(d.from)}</b> → <b>{agentTitle(d.to)}</b>
          </span>
        ))}
      </div>
    </section>
  );
}
