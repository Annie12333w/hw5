"""FastAPI backend for the Campus Customs supervisor dashboard.

Start it from the backend folder:
    uvicorn main:app --reload --port 8000

Every shop fact and every database change goes through the campus-customs MCP
server. Agents only *prepare* payments; the approve route is the one place a
human decision moves cash. Interactive docs: http://localhost:8000/docs
"""

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# `uvicorn main:app` imports this file as a top-level module, so make the
# backend package importable from the HW 5 folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend.approve import decide  # noqa: E402
from backend.audit import AuditLog, now_utc, read_events  # noqa: E402
from backend.config import MODEL, WORKING_DB  # noqa: E402
from backend.mcp_client import ShopMCP  # noqa: E402
from backend.models import (ApproveRequest, AuditEventType, Budget, CashView, EventsPage, EventView,  # noqa: E402
                            MetricsView, RejectRequest, ResolveRequest, RunRequest, RunState,
                            RunStatus, SpendLimitRequest, TicketStatus, TicketView, ToolUse)
from backend.narrate import AGENT_TITLES, describe_call, narrate_tool  # noqa: E402
from backend.reset_db import reset_working_db  # noqa: E402
from backend.spend import (get_spend_limit, last_reset_index, prices, set_spend_limit,  # noqa: E402
                           spend_since_reset, step_cost, step_tokens)
from backend.team import new_run_id, run as run_team  # noqa: E402

MAX_RESULT_CHARS = 1_500  # tool results shown on the board are trimmed to this
DASHBOARD_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One long-lived MCP session for the dashboard's reads and human decisions.
    # Each agent run opens its own session inside team.run().
    app.state.mcp = await ShopMCP().__aenter__()
    app.state.mcp_lock = asyncio.Lock()
    app.state.runs: dict[str, RunStatus] = {}
    app.state.tasks: dict[str, asyncio.Task] = {}
    app.state.llm = None  # None = PortkeyLLM (gpt-6-luna); tests may inject a fake
    try:
        yield
    finally:
        await app.state.mcp.__aexit__(None, None, None)


app = FastAPI(title="Campus Customs Backend", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=DASHBOARD_ORIGINS,  # the Vite dev page (npm run dev)
    allow_methods=["*"],
    allow_headers=["*"],
)


async def mcp_call(tool: str, args: dict) -> Any:
    async with app.state.mcp_lock:
        ok, result = await app.state.mcp.call(tool, args)
    if not ok:
        raise HTTPException(502, detail={"tool": tool, "error": result})
    return result


def active_run() -> RunStatus | None:
    return next((r for r in app.state.runs.values() if r.state == RunState.RUNNING), None)


# ----- health ----------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"ok": True, "model": MODEL, "working_db": str(WORKING_DB),
            "mcp_tools": len(app.state.mcp.tools), "active_run": (r.run_id if (r := active_run()) else None)}


# ----- tickets ---------------------------------------------------------------------------

@app.get("/tickets", response_model=list[TicketView])
async def list_tickets() -> list[TicketView]:
    result = await mcp_call("list_tickets", {})
    return [TicketView(**t, is_open=t["status"] != TicketStatus.RESOLVED.value) for t in result["tickets"]]


@app.get("/tickets/{ticket_id}")
async def ticket_detail(ticket_id: int) -> dict:
    """One ticket with its linked rows, drafts (for the human to review) and payment requests."""
    result = await mcp_call("get_ticket", {"ticket_id": ticket_id})
    if not result.get("found"):
        raise HTTPException(404, detail=f"No ticket {ticket_id}.")
    return result


@app.post("/tickets/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: int, body: ResolveRequest) -> dict:
    """The human's Mark resolved click. Refused while a payment for this ticket awaits approval."""
    note = f"Resolved by {body.resolved_by.strip()}" + (f": {body.note.strip()}" if body.note else ".")
    args = {"ticket_id": ticket_id, "agent": "human", "status": TicketStatus.RESOLVED.value, "note": note}
    result = await mcp_call("update_ticket", args)
    audit = AuditLog(f"human-{now_utc()}")
    audit.ticket_id = ticket_id
    audit.log(AuditEventType.HUMAN_DECISION, agent="human", tool="update_ticket", arguments=args,
              ok=bool(result.get("ok")), result=result)
    if not result.get("ok"):
        raise HTTPException(409, detail=result)
    return result


async def _run_and_record(status: RunStatus, reset: bool) -> None:
    try:
        # Safety rule: the human's $ limit caps spend since the last reset across all runs.
        budget = Budget(max_spend_usd=get_spend_limit())
        summary = await run_team(status.ticket_id, llm=app.state.llm, reset=reset, run_id=status.run_id,
                                 budget=budget, prior_spend_usd=spend_since_reset(read_events()))
        status.summary, status.state = summary, RunState.DONE
    except Exception as exc:  # recorded for the dashboard instead of crashing the server
        status.error, status.state = repr(exc), RunState.ERROR
    finally:
        status.finished_utc = now_utc()
        app.state.tasks.pop(status.run_id, None)


@app.post("/tickets/{ticket_id}/run", response_model=RunStatus, status_code=202)
async def run_ticket(ticket_id: int, body: RunRequest | None = None) -> RunStatus:
    body = body or RunRequest()
    if busy := active_run():
        raise HTTPException(409, detail=f"Run {busy.run_id} on ticket {busy.ticket_id} is still running.")
    ticket = await mcp_call("get_ticket", {"ticket_id": ticket_id})
    if not ticket.get("found"):
        raise HTTPException(404, detail=f"No ticket {ticket_id}.")
    spent, limit = spend_since_reset(read_events()), get_spend_limit()
    if not body.reset and spent >= limit:
        raise HTTPException(409, detail=f"Spend limit reached: ${spent:.4f} of the ${limit:g} limit since the last reset. "
                                        "Raise the limit or reset the shop data to run again.")
    status = RunStatus(run_id=new_run_id(), ticket_id=ticket_id, state=RunState.RUNNING, started_utc=now_utc())
    app.state.runs[status.run_id] = status
    task = asyncio.create_task(_run_and_record(status, body.reset))
    app.state.tasks[status.run_id] = task
    if body.wait:
        await task
    return status


@app.get("/runs/{run_id}", response_model=RunStatus)
async def get_run(run_id: str) -> RunStatus:
    if run_id not in app.state.runs:
        raise HTTPException(404, detail="Unknown run_id (runs are kept in memory until the server restarts).")
    return app.state.runs[run_id]


# ----- agent events ----------------------------------------------------------------------

def _clip(value: Any) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return value if len(text) <= MAX_RESULT_CHARS else text[:MAX_RESULT_CHARS] + "... [trimmed]"


def _event_view(cursor: int, e: dict) -> EventView:
    d = e.get("detail") or {}
    ev = e.get("event")
    said, tools, tokens, cost = None, [], None, None
    if ev == "llm_step":
        tokens, cost = sum(step_tokens(e)), round(step_cost(e), 6)
        plans = []
        for c in d.get("tool_calls") or []:
            try:
                args = json.loads(c.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = c.get("arguments")
            tools.append(ToolUse(tool=c.get("name", ""), arguments=args))
            if c.get("name") != "finish":
                plans.append(describe_call(c.get("name", ""), args if isinstance(args, dict) else {}))
        # Prefer the agent's own words; fall back to a plain-English description of its next move.
        said = (d.get("content") or "").strip() or ("Next: " + "; ".join(plans) + "." if plans else None)
    elif ev in ("tool_call", "context_loaded", "human_decision"):
        tools.append(ToolUse(tool=d.get("tool", ""), arguments=d.get("arguments"), ok=d.get("ok"),
                             result=_clip(d.get("result"))))
        said = narrate_tool(d.get("tool", ""), d.get("arguments"), d.get("result"))
    elif ev == "delegation":
        to = AGENT_TITLES.get(d.get("to_agent"), d.get("to_agent"))
        if d.get("phase") == "start":
            said = f"Handed off to {to}: {d.get('task')}"
        else:
            said = f"{to[0].upper() + to[1:]} reported back: {(d.get('report') or {}).get('summary')}"
    elif ev in ("agent_finish", "run_end"):
        said = (d.get("report") or d.get("final_report") or {}).get("summary")
    elif ev == "agent_start":
        # Hide the raw ticket/board record the system attaches to the Boss's task.
        task = str(d.get("task") or "").split("\nTicket record from MCP")[0].split("\nBoard from MCP")[0]
        said = f"Picked up the task: {task.strip()}"
    elif ev == "guardrail":
        said = f"Stopped by a safety rule: {d.get('message') or d.get('reason')}"
    elif ev == "error":
        said = f"Something went wrong ({d.get('where')}): {d.get('error') or d.get('raw')}"
    elif ev == "run_start":
        limit = (d.get("budget") or {}).get("max_spend_usd")
        said = "The team started work" + (f" (spend limit ${limit:.2f})." if limit else ".")
    elif ev == "reset":
        said = "Shop data was reset to the original database."
    return EventView(cursor=cursor, run_id=e.get("run_id", ""), seq=e.get("seq", 0), ts_utc=e.get("ts_utc", ""),
                     event=ev, ticket_id=e.get("ticket_id"), agent=e.get("agent"), chain=e.get("chain") or [],
                     step=e.get("step"), said=said, tools=tools, tokens=tokens, cost_usd=cost)


@app.get("/events", response_model=EventsPage)
async def recent_events(limit: int = Query(50, ge=1, le=500),
                        since: int | None = Query(None, ge=0, description="next_cursor from the last call"),
                        ticket_id: int | None = None, run_id: str | None = None,
                        include_before_reset: bool = False) -> EventsPage:
    """Events for the board. By default only the current session: everything after the last reset.
    Older runs stay in audit_trail.json; pass include_before_reset=true to see them."""
    raw = read_events()
    start = 0 if include_before_reset else last_reset_index(raw) + 1
    indexed = list(enumerate(raw))[max(start, since or 0):]
    if ticket_id is not None:
        indexed = [(i, e) for i, e in indexed if e.get("ticket_id") == ticket_id]
    if run_id is not None:
        indexed = [(i, e) for i, e in indexed if e.get("run_id") == run_id]
    return EventsPage(events=[_event_view(i, e) for i, e in indexed[-limit:]], next_cursor=len(raw), total=len(raw))


# ----- payments (human approval) ---------------------------------------------------------

@app.get("/payments/pending")
async def pending_payments() -> dict:
    return await mcp_call("list_payment_requests", {"status": "pending_approval"})


@app.post("/payments/{request_id}/approve")
async def approve_payment(request_id: int, body: ApproveRequest | None = None) -> dict:
    body = body or ApproveRequest()
    """The human click. This is the only route that moves cash (invoice, rent or purchase order)."""
    async with app.state.mcp_lock:
        ok, result = await decide(app.state.mcp, "approve_payment",
                                  {"request_id": request_id, "approved_by": body.approved_by})
    if not ok or not (isinstance(result, dict) and result.get("ok")):
        raise HTTPException(409, detail=result)
    return result


@app.post("/payments/{request_id}/reject")
async def reject_payment(request_id: int, body: RejectRequest) -> dict:
    async with app.state.mcp_lock:
        ok, result = await decide(app.state.mcp, "reject_payment",
                                  {"request_id": request_id, "rejected_by": body.rejected_by, "reason": body.reason})
    if not ok or not (isinstance(result, dict) and result.get("ok")):
        raise HTTPException(409, detail=result)
    return result


# ----- cash ------------------------------------------------------------------------------

@app.get("/cash", response_model=CashView)
async def cash() -> CashView:
    result = await mcp_call("get_cash_balance", {"account": "checking"})
    if not result.get("found"):
        raise HTTPException(404, detail="No checking account in cash_accounts.")
    return CashView(account=result["name"], **{k: result[k] for k in (
        "balance", "date", "pending_requests", "pending_total", "available_after_pending")})


# ----- metrics bar -----------------------------------------------------------------------

@app.get("/metrics", response_model=MetricsView)
async def metrics() -> MetricsView:
    """Shop date, ticket counts, cash, and agent spend (tokens) since the last reset and all time."""
    desk = await mcp_call("get_shop_date", {})
    tickets = (await mcp_call("list_tickets", {}))["tickets"]
    money = await mcp_call("get_cash_balance", {"account": "checking"})
    events = read_events()
    last_reset = last_reset_index(events)
    # Spend is summed from every LLM step as it is logged, so the bar moves during a run.
    steps = [(i, e) for i, e in enumerate(events) if e.get("event") == "llm_step"]
    recent = [e for i, e in steps if i > last_reset]
    busy = active_run()
    resolved = sum(t["status"] == TicketStatus.RESOLVED.value for t in tickets)
    run_cap = Budget().max_total_tokens
    spent, limit, price = sum(step_cost(e) for e in recent), get_spend_limit(), prices()
    return MetricsView(
        spend_since_reset_usd=round(spent, 6), spend_limit_usd=limit, limit_reached=spent >= limit,
        spend_all_time_usd=round(sum(step_cost(e) for _, e in steps), 6),
        active_run_spend_usd=round(sum(step_cost(e) for e in recent if busy and e.get("run_id") == busy.run_id), 6),
        price_input_per_million_usd=price["input_per_million_usd"],
        price_output_per_million_usd=price["output_per_million_usd"],
        shop_date=desk.get("date_today"), open_tickets=len(tickets) - resolved, resolved_tickets=resolved,
        cash_balance=money.get("balance", 0.0), cash_pending=money.get("pending_total", 0.0),
        cash_available_after_pending=money.get("available_after_pending", 0.0),
        runs_since_reset=sum(1 for i, e in enumerate(events) if e.get("event") == "run_start" and i > last_reset),
        llm_calls_since_reset=len(recent),
        tokens_since_reset=sum(sum(step_tokens(e)) for e in recent),
        tokens_all_time=sum(sum(step_tokens(e)) for _, e in steps),
        run_token_budget=run_cap,
        board_token_budget=run_cap * max(1, len(tickets)),
        active_run_id=busy.run_id if busy else None, active_ticket_id=busy.ticket_id if busy else None,
        active_run_tokens=sum(sum(step_tokens(e)) for e in recent if busy and e.get("run_id") == busy.run_id),
    )


# ----- spend limit (human setting + backend safety rule) ----------------------------------

@app.get("/settings")
async def get_settings() -> dict:
    return {"spend_limit_usd": get_spend_limit(), **prices()}


@app.put("/settings/spend-limit")
async def update_spend_limit(body: SpendLimitRequest) -> dict:
    """The human sets the $ limit. Agents stop once spend since the last reset reaches it."""
    limit = set_spend_limit(body.limit_usd)
    AuditLog(f"human-{now_utc()}").log(AuditEventType.HUMAN_DECISION, agent="human", tool="set_spend_limit",
                                        arguments={"limit_usd": limit}, ok=True, result={"spend_limit_usd": limit})
    return {"ok": True, "spend_limit_usd": limit}


# ----- reset -----------------------------------------------------------------------------

@app.post("/reset")
async def reset() -> dict:
    """Restore campus_customs_new.db from campus_customs.db for a fresh run. The audit trail is kept."""
    if busy := active_run():
        raise HTTPException(409, detail=f"Run {busy.run_id} is still running; reset after it finishes.")
    async with app.state.mcp_lock:
        info = reset_working_db()
    AuditLog(f"reset-{info['at_utc']}").log(AuditEventType.RESET, agent="human", **info)
    return {"ok": True, **info, "cash": (await cash()).model_dump()}
