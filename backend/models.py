"""Data types shared by the Campus Customs agent team."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


DEFAULT_SUPERVISOR = "Supervisor #1"  # approver name used when the human leaves it blank


class AgentName(str, Enum):
    BOSS = "boss"
    INVENTORY = "inventory"
    ACCOUNTING = "accounting"
    FACILITIES = "facilities"
    CUSTOMER_SERVICE = "customer_service"


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_APPROVAL = "waiting_approval"
    BLOCKED = "blocked"
    RESOLVED = "resolved"


class PaymentKind(str, Enum):
    INVOICE = "invoice"
    RENT = "rent"
    PURCHASE_ORDER = "purchase_order"


class DraftKind(str, Enum):
    CUSTOMER_MESSAGE = "customer_message"
    VENDOR_MESSAGE = "vendor_message"
    LANDLORD_MESSAGE = "landlord_message"
    PURCHASE_ORDER = "purchase_order"


class AuditEventType(str, Enum):
    RUN_START = "run_start"
    CONTEXT_LOADED = "context_loaded"
    AGENT_START = "agent_start"
    LLM_STEP = "llm_step"
    TOOL_CALL = "tool_call"
    DELEGATION = "delegation"
    GUARDRAIL = "guardrail"
    AGENT_FINISH = "agent_finish"
    ERROR = "error"
    RUN_END = "run_end"
    HUMAN_DECISION = "human_decision"
    RESET = "reset"


class AgentSpec(BaseModel):
    """Static definition of one agent: who it is, its prompt file, and its MCP tool allowlist."""
    name: AgentName
    title: str
    description: str  # shown to other agents in the delegate tool
    prompt_file: str
    mcp_tools: list[str]


class Budget(BaseModel):
    """Hard limits that keep a run safe and its token use bounded."""
    max_steps_per_agent: int = 8          # LLM turns in one agent loop
    max_delegation_depth: int = 3         # boss -> a -> b -> c, no deeper
    max_agent_invocations: int = 14       # agent loops started in one run
    max_llm_calls: int = 45               # LLM requests in one run
    max_total_tokens: int = 160_000       # prompt + completion tokens in one run
    max_completion_tokens: int = 1_500    # per LLM request
    max_tool_result_chars: int = 4_000    # tool output passed back to the model
    max_task_chars: int = 1_500           # delegated task + context text
    max_spend_usd: float | None = None    # human-set $ limit on agent spend since the last reset


class Usage(BaseModel):
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    agent_invocations: int = 0
    cost_usd: float = 0.0                 # this run's spend at gpt-6-luna prices


class AgentReport(BaseModel):
    """What an agent hands back when it calls finish (to the Boss, the delegator, or the run)."""
    agent: AgentName
    summary: str = Field(description="What was found and done, citing database values.")
    recommended_ticket_status: TicketStatus | None = None
    facts: list[str] = Field(default_factory=list, description="Key values read from MCP tools.")
    human_actions_needed: list[str] = Field(default_factory=list)
    draft_ids: list[int] = Field(default_factory=list)
    payment_request_ids: list[int] = Field(default_factory=list)
    stopped_reason: str | None = None  # set when a guardrail or budget ended the loop early


class ToolCallRecord(BaseModel):
    tool: str
    arguments: dict[str, Any]
    injected: dict[str, Any] = Field(default_factory=dict)  # values the backend set, not the model
    ok: bool
    result: Any = None
    error: str | None = None
    duration_ms: int = 0


class AuditEvent(BaseModel):
    """One line of output/audit_trail.json. Enough to replay who did what, with which data, and why."""
    run_id: str
    seq: int
    ts_utc: str
    shop_date: str | None = None
    event: AuditEventType
    ticket_id: int | None = None
    agent: str | None = None              # agent name, "system" or "human"
    depth: int | None = None              # 0 = Boss at the top of the run
    chain: list[str] = Field(default_factory=list)  # delegation path to this agent
    step: int | None = None               # LLM step within this agent loop
    model: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class RunSummary(BaseModel):
    run_id: str
    ticket_id: int | None
    model: str
    started_utc: str
    finished_utc: str
    shop_date: str | None
    final_report: AgentReport
    usage: Usage
    budget: Budget


# ----- API types (backend/main.py) ------------------------------------------------------

class TicketView(BaseModel):
    id: int
    type: str
    requester: str
    subject: str
    status: TicketStatus | str
    is_open: bool                          # False only when status is "resolved"
    sku: str | None = None
    size: str | None = None
    qty: int | None = None
    lease_id: int | None = None
    invoice_id: int | None = None
    notes: str | None = None
    created_at: str


class RunRequest(BaseModel):
    reset: bool = False   # restore the working DB from the original before this run
    wait: bool = False    # True = respond only when the run finishes; False = start it and poll


class RunState(str, Enum):
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class RunStatus(BaseModel):
    run_id: str
    ticket_id: int
    state: RunState
    started_utc: str
    finished_utc: str | None = None
    summary: RunSummary | None = None
    error: str | None = None


class ToolUse(BaseModel):
    tool: str
    arguments: Any = None
    ok: bool | None = None                 # None = requested by the model, not yet run
    result: Any = None


class EventView(BaseModel):
    """One audit event, trimmed for the board: who acted, what they said, which tools they used."""
    cursor: int                            # position in audit_trail.json
    run_id: str
    seq: int
    ts_utc: str
    event: AuditEventType | str
    ticket_id: int | None = None
    agent: str | None = None
    chain: list[str] = Field(default_factory=list)
    step: int | None = None
    said: str | None = None
    tools: list[ToolUse] = Field(default_factory=list)
    tokens: int | None = None              # prompt + completion tokens of this LLM step
    cost_usd: float | None = None          # dollar cost of this LLM step


class EventsPage(BaseModel):
    events: list[EventView]
    next_cursor: int                       # pass back as ?since= to get only newer events
    total: int


class ApproveRequest(BaseModel):
    approved_by: str = Field(DEFAULT_SUPERVISOR, min_length=1, description="Human approver; defaults to Supervisor #1.")


class RejectRequest(BaseModel):
    rejected_by: str = Field(DEFAULT_SUPERVISOR, min_length=1)
    reason: str = Field(min_length=1)


class ResolveRequest(BaseModel):
    resolved_by: str = Field(DEFAULT_SUPERVISOR, min_length=1, description="Human supervisor; defaults to Supervisor #1.")
    note: str | None = None


class MetricsView(BaseModel):
    """The dashboard's top metrics bar."""
    shop_date: str | None
    open_tickets: int
    resolved_tickets: int
    cash_balance: float
    cash_pending: float
    cash_available_after_pending: float
    runs_since_reset: int
    llm_calls_since_reset: int             # counted live from each LLM step
    tokens_since_reset: int                # counted live from each LLM step
    tokens_all_time: int
    run_token_budget: int                  # Budget.max_total_tokens: hard cap for one run
    board_token_budget: int                # run cap x number of tickets: scale for the spend bar
    active_run_id: str | None = None
    active_ticket_id: int | None = None
    active_run_tokens: int = 0
    spend_since_reset_usd: float = 0.0     # what the spend bar shows
    spend_limit_usd: float = 0.0           # the human-set limit (bar scale and safety stop)
    spend_all_time_usd: float = 0.0
    active_run_spend_usd: float = 0.0
    limit_reached: bool = False
    price_input_per_million_usd: float = 0.0
    price_output_per_million_usd: float = 0.0


class SpendLimitRequest(BaseModel):
    limit_usd: float = Field(gt=0, le=1000, description="Dollar limit on agent token spend since the last reset.")


class CashView(BaseModel):
    account: str
    balance: float
    date: str
    pending_requests: int
    pending_total: float
    available_after_pending: float
