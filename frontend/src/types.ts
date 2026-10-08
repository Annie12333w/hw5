// Mirrors backend/models.py (API types). Keep in sync when the backend changes.

export type AgentName = "boss" | "inventory" | "accounting" | "facilities" | "customer_service";
export type TicketStatus = "open" | "in_progress" | "waiting_approval" | "blocked" | "resolved";

export interface Ticket {
  id: number;
  type: string;
  requester: string;
  subject: string;
  status: TicketStatus;
  is_open: boolean;
  sku: string | null;
  size: string | null;
  qty: number | null;
  lease_id: number | null;
  invoice_id: number | null;
  notes: string | null;
  created_at: string;
}

export interface AgentReport {
  agent: AgentName;
  summary: string;
  recommended_ticket_status: TicketStatus | null;
  facts: string[];
  human_actions_needed: string[];
  draft_ids: number[];
  payment_request_ids: number[];
  stopped_reason: string | null;
}

export interface Usage {
  llm_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  agent_invocations: number;
}

export interface RunSummary {
  run_id: string;
  ticket_id: number | null;
  model: string;
  started_utc: string;
  finished_utc: string;
  shop_date: string | null;
  final_report: AgentReport;
  usage: Usage;
}

export type RunState = "running" | "done" | "error";

export interface RunStatus {
  run_id: string;
  ticket_id: number;
  state: RunState;
  started_utc: string;
  finished_utc: string | null;
  summary: RunSummary | null;
  error: string | null;
}

export interface ToolUse {
  tool: string;
  arguments: unknown;
  ok: boolean | null;
  result: unknown;
}

export type EventType =
  | "run_start" | "context_loaded" | "agent_start" | "llm_step" | "tool_call" | "delegation"
  | "guardrail" | "agent_finish" | "error" | "run_end" | "human_decision" | "reset";

export interface AgentEvent {
  cursor: number;
  run_id: string;
  seq: number;
  ts_utc: string;
  event: EventType;
  ticket_id: number | null;
  agent: string | null;
  chain: string[];
  step: number | null;
  said: string | null;
  tools: ToolUse[];
  tokens: number | null;
  cost_usd: number | null;
}

export interface EventsPage {
  events: AgentEvent[];
  next_cursor: number;
  total: number;
}

export interface PaymentRequest {
  id: number;
  kind: "invoice" | "rent" | "purchase_order";
  ref_id: number;
  amount: number;
  payee: string;
  account: string;
  ticket_id: number;
  reason: string;
  requested_by: string;
  run_id: string | null;
  shop_date: string;
  created_at_utc: string;
  status: "pending_approval" | "paid" | "rejected" | "refused";
  decided_by?: string;
  decided_at_utc?: string;
  payment_id?: number;
  decision_note?: string;
}

export interface Draft {
  id: number;
  ticket_id: number;
  kind: "customer_message" | "vendor_message" | "landlord_message" | "purchase_order";
  recipient: string;
  subject?: string;
  body?: string;
  author_agent: string;
  status: string;
  // purchase-order fields
  sku?: string;
  size?: string;
  qty?: number;
  unit_cost?: number;
  total?: number;
  expected_arrival_if_ordered_today?: string;
  vendor_will_ship?: boolean;
}

export interface IncomingStock {
  id: number;
  sku: string;
  size: string;
  name: string | null;
  qty: number | null;          // null = quantity not recorded (e.g. an invoice reprint)
  vendor: string;
  expected_arrival: string;
  source: string;
  status: string;
}

export interface TicketDetail {
  found: boolean;
  date_today: string;
  ticket: Omit<Ticket, "is_open">;
  invoice?: { id: number; vendor_id: number; amount: number; due_date: string; status: string; description: string | null } | null;
  invoice_vendor?: { id: number; name: string; specialty: string; lead_days: number } | null;
  lease?: { id: number; space_name: string; landlord: string; monthly_rent: number; next_due: string; notes: string | null } | null;
  inventory?: { sku: string; name: string; size: string; qty: number; location: string }[];
  pricing?: { sku: string; unit_cost: number; list_price: number } | null;
  incoming?: IncomingStock[];
  drafts: Draft[];
  payment_requests: PaymentRequest[];
}

export interface Metrics {
  shop_date: string | null;
  open_tickets: number;
  resolved_tickets: number;
  cash_balance: number;
  cash_pending: number;
  cash_available_after_pending: number;
  runs_since_reset: number;
  llm_calls_since_reset: number;
  tokens_since_reset: number;
  tokens_all_time: number;
  run_token_budget: number;
  board_token_budget: number;
  active_run_id: string | null;
  active_ticket_id: number | null;
  active_run_tokens: number;
  spend_since_reset_usd: number;
  spend_limit_usd: number;
  spend_all_time_usd: number;
  active_run_spend_usd: number;
  limit_reached: boolean;
  price_input_per_million_usd: number;
  price_output_per_million_usd: number;
}
