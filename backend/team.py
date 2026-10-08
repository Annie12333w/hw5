"""The Campus Customs agent team: agent loops, any-to-any delegation, guardrails and audit.

Every agent runs the same loop:
  1. Send its system prompt, task and tool list to gpt-6-luna (via Portkey).
  2. Run each tool call the model asks for:
       - an MCP tool on that agent's allowlist (shop data and writes),
       - delegate(to_agent, task): runs another agent's loop and returns its report,
       - finish(...): ends the loop with an AgentReport.
  3. Feed tool results back and repeat, within the Budget.
Every step is appended to output/audit_trail.json.
"""

import copy
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .agents import AGENTS, HUMAN_ONLY_TOOLS, load_prompt
from .audit import AuditLog, now_utc
from .config import MODEL, WORKING_DB
from .llm import ChatLLM, PortkeyLLM
from .mcp_client import ShopMCP
from .models import (AgentName, AgentReport, AgentSpec, AuditEventType as EV, Budget,
                     RunSummary, TicketStatus, Usage)
from .reset_db import reset_working_db
from .spend import cost_usd

# Parameters the backend fills in itself so a model cannot spoof who did what.
INJECTED_PARAMS = ("agent", "run_id")
# Tools that change state. In a single-ticket run they may only touch that ticket.
WRITE_TOOLS = frozenset({"update_ticket", "save_draft", "draft_purchase_order", "request_payment"})


def _fn(name: str, description: str, parameters: dict) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


FINISH_TOOL = _fn(
    "finish",
    "End your turn and hand your report back to whoever gave you the task. "
    "Cite database values; list anything a human must approve or review.",
    {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "What you found and did, with the database values."},
            "recommended_ticket_status": {"type": ["string", "null"], "enum": [s.value for s in TicketStatus] + [None]},
            "facts": {"type": "array", "items": {"type": "string"}},
            "human_actions_needed": {"type": "array", "items": {"type": "string"}},
            "draft_ids": {"type": "array", "items": {"type": "integer"}},
            "payment_request_ids": {"type": "array", "items": {"type": "integer"}},
        },
        "required": ["summary"],
    },
)


class Team:
    def __init__(self, mcp: ShopMCP, llm: ChatLLM, audit: AuditLog, budget: Budget,
                 run_id: str, ticket_id: int | None, prior_spend_usd: float = 0.0):
        self.mcp, self.llm, self.audit, self.budget = mcp, llm, audit, budget
        self.run_id, self.ticket_id = run_id, ticket_id
        self.prior_spend_usd = prior_spend_usd  # spent by earlier runs since the last reset
        self.usage = Usage()

    def spent_usd(self) -> float:
        return self.prior_spend_usd + self.usage.cost_usd

    # ----- tool schemas -------------------------------------------------------------

    def _tool_schemas(self, spec: AgentSpec) -> list[dict]:
        tools = []
        for name in spec.mcp_tools:
            if name not in self.mcp.tools:
                continue
            schema = copy.deepcopy(self.mcp.input_schema(name))
            props = schema.get("properties", {})
            for p in INJECTED_PARAMS:
                props.pop(p, None)
            schema["required"] = [r for r in schema.get("required", []) if r not in INJECTED_PARAMS]
            tools.append(_fn(name, self.mcp.description(name), schema))
        others = [s for n, s in AGENTS.items() if n != spec.name]
        roster = "; ".join(f"{s.name.value}: {s.description}" for s in others)
        tools.append(_fn(
            "delegate",
            "Hand a sub-task to another agent and wait for its report. Any agent may delegate to any "
            f"other agent. Team: {roster}",
            {"type": "object",
             "properties": {
                 "to_agent": {"type": "string", "enum": [s.name.value for s in others]},
                 "task": {"type": "string", "description": "One clear, specific question or job."},
                 "context": {"type": "string", "description": "Facts you already have (with values) so they need not re-check."},
             },
             "required": ["to_agent", "task"]},
        ))
        tools.append(FINISH_TOOL)
        return tools

    # ----- budget -------------------------------------------------------------------

    def _budget_exhausted(self) -> str | None:
        b, u = self.budget, self.usage
        if u.llm_calls >= b.max_llm_calls:
            return f"run LLM-call limit reached ({b.max_llm_calls})"
        if u.total_tokens >= b.max_total_tokens:
            return f"run token limit reached ({b.max_total_tokens})"
        if b.max_spend_usd is not None and self.spent_usd() >= b.max_spend_usd:
            return f"dollar spend limit reached (${self.spent_usd():.4f} of the ${b.max_spend_usd:g} limit)"
        return None

    def _count(self, usage: Any) -> dict:
        self.usage.llm_calls += 1
        if usage is None:
            return {}
        pt = getattr(usage, "prompt_tokens", 0) or 0
        ct = getattr(usage, "completion_tokens", 0) or 0
        self.usage.prompt_tokens += pt
        self.usage.completion_tokens += ct
        self.usage.total_tokens += pt + ct
        step_cost = cost_usd(pt, ct)
        self.usage.cost_usd += step_cost
        return {"prompt_tokens": pt, "completion_tokens": ct, "cost_usd": round(step_cost, 6)}

    def _clip(self, result: Any) -> str:
        text = json.dumps(result, ensure_ascii=False, default=str)
        limit = self.budget.max_tool_result_chars
        return text if len(text) <= limit else text[:limit] + f"... [truncated from {len(text)} chars]"

    def _brief(self, spec: AgentSpec, task: str, chain: list[str], depth: int) -> str:
        b, u = self.budget, self.usage
        scope = f"ticket {self.ticket_id}" if self.ticket_id is not None else "all open tickets on the board"
        return (
            f"Run {self.run_id}. You are {spec.title}. Delegation chain: {' -> '.join(chain)} "
            f"(depth {depth} of max {b.max_delegation_depth}).\n"
            f"Scope: {scope}.\n"
            f"Team budget left: {b.max_llm_calls - u.llm_calls} LLM calls, "
            f"{b.max_total_tokens - u.total_tokens} tokens"
            + (f", ${b.max_spend_usd - self.spent_usd():.4f} left of the ${b.max_spend_usd:.2f} spend limit"
               if b.max_spend_usd else "")
            + f". You have at most {b.max_steps_per_agent} steps.\n\n"
            f"TASK:\n{task}"
        )

    def _stopped(self, name: AgentName, reason: str, chain: list[str], depth: int) -> AgentReport:
        self.audit.log(EV.GUARDRAIL, agent=name.value, depth=depth, chain=chain, rule="budget_or_limit", reason=reason)
        return AgentReport(agent=name, summary=f"Stopped before finishing: {reason}.",
                           human_actions_needed=["Review this ticket manually; the agent hit a limit."],
                           stopped_reason=reason)

    # ----- agent loop ---------------------------------------------------------------

    async def run_agent(self, name: AgentName, task: str, chain: list[str], depth: int) -> AgentReport:
        spec = AGENTS[name]
        chain = chain + [name.value]
        if self.usage.agent_invocations >= self.budget.max_agent_invocations:
            return self._stopped(name, f"agent-invocation limit reached ({self.budget.max_agent_invocations})", chain, depth)
        self.usage.agent_invocations += 1

        tools = self._tool_schemas(spec)
        messages: list[dict] = [
            {"role": "system", "content": load_prompt(spec)},
            {"role": "user", "content": self._brief(spec, task, chain, depth)},
        ]
        self.audit.log(EV.AGENT_START, agent=name.value, depth=depth, chain=chain,
                       task=task, tools=[t["function"]["name"] for t in tools])

        for step in range(1, self.budget.max_steps_per_agent + 1):
            reason = self._budget_exhausted()
            if reason:
                return self._stopped(name, reason, chain, depth)
            forced = step == self.budget.max_steps_per_agent
            tool_choice = {"type": "function", "function": {"name": "finish"}} if forced else "auto"
            try:
                resp = await self.llm(messages=messages, tools=tools, tool_choice=tool_choice,
                                      max_completion_tokens=self.budget.max_completion_tokens)
            except Exception as exc:  # network / provider errors end this agent, not the run
                self.audit.log(EV.ERROR, agent=name.value, depth=depth, chain=chain, step=step,
                               model=MODEL, where="llm_call", error=repr(exc))
                return AgentReport(agent=name, summary=f"LLM call failed: {exc!r}", stopped_reason="llm_error",
                                   human_actions_needed=["Re-run or handle manually; the model call failed."])

            step_usage = self._count(getattr(resp, "usage", None))
            choice = resp.choices[0]
            msg = choice.message
            calls = list(msg.tool_calls or [])
            self.audit.log(EV.LLM_STEP, agent=name.value, depth=depth, chain=chain, step=step, model=MODEL,
                           finish_reason=choice.finish_reason, forced_finish=forced,
                           content=msg.content,
                           tool_calls=[{"id": c.id, "name": c.function.name, "arguments": c.function.arguments}
                                       for c in calls],
                           usage=step_usage, run_usage=self.usage.model_dump())

            messages.append({
                "role": "assistant", "content": msg.content,
                **({"tool_calls": [{"id": c.id, "type": "function",
                                    "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                   for c in calls]} if calls else {}),
            })
            if not calls:
                messages.append({"role": "user", "content": "Call a tool, or call finish with your report."})
                continue

            for call in calls:
                tool = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                    if not isinstance(args, dict):
                        raise ValueError("arguments must be a JSON object")
                except (json.JSONDecodeError, ValueError) as exc:
                    result: Any = {"ok": False, "message": f"Bad JSON arguments: {exc}"}
                    self.audit.log(EV.ERROR, agent=name.value, depth=depth, chain=chain, step=step,
                                   where="tool_arguments", tool=tool, raw=call.function.arguments)
                else:
                    if tool == "finish":
                        report = self._finish(name, args, chain, depth, step)
                        return report
                    result = await self._dispatch(spec, tool, args, chain, depth, step)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": self._clip(result)})

        return self._stopped(name, f"step limit reached ({self.budget.max_steps_per_agent})", chain, depth)

    def _finish(self, name: AgentName, args: dict, chain: list[str], depth: int, step: int) -> AgentReport:
        status = args.get("recommended_ticket_status")
        try:
            report = AgentReport(
                agent=name, summary=str(args.get("summary", "")),
                recommended_ticket_status=TicketStatus(status) if status else None,
                facts=[str(x) for x in args.get("facts") or []],
                human_actions_needed=[str(x) for x in args.get("human_actions_needed") or []],
                draft_ids=[int(x) for x in args.get("draft_ids") or []],
                payment_request_ids=[int(x) for x in args.get("payment_request_ids") or []],
            )
        except (ValueError, TypeError) as exc:
            report = AgentReport(agent=name, summary=str(args.get("summary", "")),
                                 stopped_reason=f"finish arguments invalid: {exc}")
        self.audit.log(EV.AGENT_FINISH, agent=name.value, depth=depth, chain=chain, step=step,
                       report=report.model_dump(mode="json"))
        return report

    async def _dispatch(self, spec: AgentSpec, tool: str, args: dict, chain: list[str],
                        depth: int, step: int) -> Any:
        def block(rule: str, message: str) -> dict:
            self.audit.log(EV.GUARDRAIL, agent=spec.name.value, depth=depth, chain=chain, step=step,
                           rule=rule, tool=tool, arguments=args, message=message)
            return {"ok": False, "blocked_by_guardrail": rule, "message": message}

        if tool in HUMAN_ONLY_TOOLS:
            return block("human_only_tool", f"{tool} can only be run by the human supervisor. Use request_payment.")
        if tool == "delegate":
            return await self._delegate(spec, args, chain, depth, step)
        if tool not in spec.mcp_tools or tool not in self.mcp.tools:
            return block("tool_not_allowed", f"{spec.title} is not allowed to call {tool}. Delegate instead.")
        if (tool in WRITE_TOOLS and self.ticket_id is not None
                and "ticket_id" in args and args["ticket_id"] != self.ticket_id):
            return block("ticket_scope", f"This run may only change ticket {self.ticket_id}.")

        props = self.mcp.input_schema(tool).get("properties", {})
        injected = {}
        if "agent" in props:
            injected["agent"] = spec.name.value
        if "run_id" in props:
            injected["run_id"] = self.run_id
        call_args = {**args, **injected}

        started = time.perf_counter()
        try:
            ok, result = await self.mcp.call(tool, call_args)
            error = None if ok else "tool returned an error"
        except Exception as exc:
            ok, result, error = False, {"ok": False, "message": f"MCP call failed: {exc!r}"}, repr(exc)
        self.audit.log(EV.TOOL_CALL, agent=spec.name.value, depth=depth, chain=chain, step=step,
                       tool=tool, arguments=args, injected=injected, ok=ok, error=error,
                       duration_ms=int((time.perf_counter() - started) * 1000), result=result)
        return result

    async def _delegate(self, spec: AgentSpec, args: dict, chain: list[str], depth: int, step: int) -> dict:
        to = str(args.get("to_agent", ""))
        task = str(args.get("task", "")).strip()
        context = str(args.get("context", "")).strip()

        def block(rule: str, message: str) -> dict:
            self.audit.log(EV.GUARDRAIL, agent=spec.name.value, depth=depth, chain=chain, step=step,
                           rule=rule, tool="delegate", arguments=args, message=message)
            return {"ok": False, "blocked_by_guardrail": rule, "message": message}

        if to not in {a.value for a in AGENTS} or to == spec.name.value:
            return block("bad_delegate_target", "to_agent must be a different team member.")
        if to in chain:
            return block("delegation_cycle",
                         f"{to} is already waiting on you in this chain ({' -> '.join(chain)}). "
                         "Put what it needs in your finish report instead.")
        if depth + 1 > self.budget.max_delegation_depth:
            return block("delegation_depth", f"Max delegation depth {self.budget.max_delegation_depth} reached; "
                                             "finish with what you have.")
        if not task:
            return block("empty_task", "Give the delegate a specific task.")

        text = task + (f"\n\nCONTEXT FROM {spec.title.upper()}:\n{context}" if context else "")
        text = text[: self.budget.max_task_chars]
        self.audit.log(EV.DELEGATION, agent=spec.name.value, depth=depth, chain=chain, step=step,
                       phase="start", to_agent=to, task=text)
        report = await self.run_agent(AgentName(to), text, chain, depth + 1)
        self.audit.log(EV.DELEGATION, agent=spec.name.value, depth=depth, chain=chain, step=step,
                       phase="end", to_agent=to, report=report.model_dump(mode="json"))
        return {"ok": True, "delegated_to": to, "report": report.model_dump(mode="json")}


# ----- run entry points ---------------------------------------------------------------

def new_run_id() -> str:
    return f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"


async def run(ticket_id: int | None = None, *, llm: ChatLLM | None = None, budget: Budget | None = None,
              reset: bool = False, run_id: str | None = None, prior_spend_usd: float = 0.0) -> RunSummary:
    """Run the team on one ticket (ticket_id) or on the whole open board (ticket_id=None).

    The Boss always starts. reset=True restores the working database from the original first.
    """
    budget = budget or Budget()
    run_id = run_id or new_run_id()
    started = now_utc()
    reset_info = reset_working_db() if reset else None
    audit = AuditLog(run_id)
    audit.ticket_id = ticket_id
    if reset_info:
        audit.log(EV.RESET, agent="system", **reset_info)  # restarts the spend-limit counter
    llm = llm or PortkeyLLM()

    async with ShopMCP() as mcp:
        _, desk = await mcp.call("get_shop_date", {})
        audit.shop_date = desk.get("date_today") if isinstance(desk, dict) else None
        audit.log(EV.RUN_START, agent="system", model=MODEL,
                  mode="ticket" if ticket_id is not None else "board", working_db=str(WORKING_DB),
                  reset=reset_info, budget=budget.model_dump(),
                  mcp_tools=sorted(mcp.tools))

        team = Team(mcp, llm, audit, budget, run_id, ticket_id,
                    prior_spend_usd=0.0 if reset else prior_spend_usd)
        if ticket_id is not None:
            ok, ctx = await mcp.call("get_ticket", {"ticket_id": ticket_id})
            audit.log(EV.CONTEXT_LOADED, agent="system", tool="get_ticket",
                      arguments={"ticket_id": ticket_id}, ok=ok, result=ctx)
            if not (isinstance(ctx, dict) and ctx.get("found")):
                report = AgentReport(agent=AgentName.BOSS, summary=f"Ticket {ticket_id} not found.",
                                     stopped_reason="ticket_not_found")
            else:
                task = (f"Work ticket {ticket_id} as far as the rules allow, then make the final call.\n"
                        f"Ticket record from MCP get_ticket:\n{team._clip(ctx)}")
                report = await team.run_agent(AgentName.BOSS, task, [], 0)
        else:
            ok, ctx = await mcp.call("list_tickets", {})
            board = [t for t in (ctx.get("tickets", []) if isinstance(ctx, dict) else [])
                     if t.get("status") != "resolved"]
            audit.log(EV.CONTEXT_LOADED, agent="system", tool="list_tickets", arguments={}, ok=ok,
                      result={"unresolved": board})
            task = ("Work every unresolved ticket on the board. Rank them first (money due soonest and "
                    "blockers first, since cash is shared), then work them in that order and make the final "
                    f"call on each.\nBoard from MCP list_tickets:\n{team._clip(board)}")
            report = await team.run_agent(AgentName.BOSS, task, [], 0)

        summary = RunSummary(run_id=run_id, ticket_id=ticket_id, model=MODEL, started_utc=started,
                             finished_utc=now_utc(), shop_date=audit.shop_date, final_report=report,
                             usage=team.usage, budget=budget)
        audit.log(EV.RUN_END, agent="system", final_report=report.model_dump(mode="json"),
                  usage=team.usage.model_dump())
    return summary
