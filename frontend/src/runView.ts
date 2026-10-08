// Turns the raw audit events of one run into what the desk shows:
// who is working, who is waiting on whom, what each agent last said, and per-agent summaries.
import { isAgent } from "./agents";
import type { AgentEvent, AgentName } from "./types";

export type AgentState = "idle" | "working" | "waiting" | "done" | "stopped";

export interface AgentView {
  state: AgentState;
  lastSaid: string | null;
  waitingOn: AgentName | null;
  calledBy: string | null;
  toolsUsed: string[];
  summaries: string[];
  steps: number;
  tokens: number;
  costUsd: number;
}

export interface Delegation { from: AgentName; to: AgentName; cursor: number }

export interface RunView {
  runId: string | null;
  started: string | null;
  finished: boolean;
  finalSummary: string | null;
  agents: Record<AgentName, AgentView>;
  delegations: Delegation[];
  activeChain: AgentName[];
  guardrails: number;
  llmSteps: number;
  tokens: number;
  costUsd: number;
  stoppedReason: string | null;
}

const blank = (): AgentView => ({
  state: "idle", lastSaid: null, waitingOn: null, calledBy: null, toolsUsed: [], summaries: [], steps: 0, tokens: 0, costUsd: 0,
});

export function runIds(events: AgentEvent[]): string[] {
  const ids: string[] = [];
  for (const e of events) if (e.event === "run_start" && !ids.includes(e.run_id)) ids.push(e.run_id);
  return ids;
}

/** Events of one run, plus the human decisions on this ticket that came after it started. */
export function eventsForRun(events: AgentEvent[], runId: string | null): AgentEvent[] {
  if (!runId) return events.filter((e) => e.agent === "human");
  const start = events.find((e) => e.run_id === runId && e.event === "run_start")?.cursor ?? 0;
  return events.filter((e) => e.run_id === runId || (e.agent === "human" && e.cursor >= start));
}

export function buildRunView(events: AgentEvent[], runId: string | null): RunView {
  const agents = {
    boss: blank(), inventory: blank(), accounting: blank(), facilities: blank(), customer_service: blank(),
  } as Record<AgentName, AgentView>;
  const view: RunView = {
    runId, started: null, finished: false, finalSummary: null, agents, delegations: [],
    activeChain: [], guardrails: 0, llmSteps: 0, tokens: 0, costUsd: 0, stoppedReason: null,
  };
  const chainOf = (e: AgentEvent) => e.chain.filter(isAgent) as AgentName[];

  for (const e of events) {
    if (e.run_id !== runId) continue;
    const who = isAgent(e.agent) ? e.agent : null;
    switch (e.event) {
      case "run_start":
        view.started = e.ts_utc;
        break;
      case "agent_start": {
        if (!who) break;
        const chain = chainOf(e);
        const caller = chain.length > 1 ? chain[chain.length - 2] : null;
        agents[who].state = "working";
        agents[who].calledBy = caller ?? "system";
        if (caller) {
          view.delegations.push({ from: caller, to: who, cursor: e.cursor });
          agents[caller].state = "waiting";
          agents[caller].waitingOn = who;
        }
        view.activeChain = chain;
        break;
      }
      case "llm_step":
        if (!who) break;
        view.llmSteps += 1;
        agents[who].steps += 1;
        agents[who].tokens += e.tokens ?? 0;
        view.tokens += e.tokens ?? 0;
        agents[who].costUsd += e.cost_usd ?? 0;
        view.costUsd += e.cost_usd ?? 0;
        if (e.said) agents[who].lastSaid = e.said;
        view.activeChain = chainOf(e);
        break;
      case "tool_call":
        if (!who) break;
        e.tools.forEach((t) => agents[who].toolsUsed.push(t.tool));
        break;
      case "delegation":
        if (!who) break;
        if (e.said?.startsWith("Delegated to")) agents[who].lastSaid = e.said;
        else {
          agents[who].state = "working";
          agents[who].waitingOn = null;
          view.activeChain = chainOf(e);
        }
        break;
      case "guardrail":
        view.guardrails += 1;
        if (who && e.said?.includes("limit")) agents[who].state = "stopped";
        break;
      case "agent_finish":
        if (!who) break;
        agents[who].state = agents[who].state === "stopped" ? "stopped" : "done";
        agents[who].waitingOn = null;
        if (e.said) {
          agents[who].summaries.push(e.said);
          agents[who].lastSaid = e.said;
        }
        view.activeChain = chainOf(e).slice(0, -1);
        break;
      case "run_end":
        view.finished = true;
        view.finalSummary = e.said;
        if (e.said?.startsWith("Stopped before finishing:")) {
          view.stoppedReason = e.said.replace("Stopped before finishing: ", "").replace(/\.$/, "");
        }
        view.activeChain = [];
        (Object.keys(agents) as AgentName[]).forEach((a) => {
          if (agents[a].state === "working" || agents[a].state === "waiting") agents[a].state = "stopped";
        });
        break;
    }
  }
  return view;
}
