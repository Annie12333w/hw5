// Thin client for the FastAPI backend (backend/main.py) at http://localhost:8000.
import type { EventsPage, Metrics, PaymentRequest, RunStatus, Ticket, TicketDetail } from "./types";

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : (detail as { message?: string })?.message ?? `HTTP ${status}`);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? body);
  return body as T;
}

const post = <T>(path: string, data?: unknown) =>
  request<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });

export const api = {
  tickets: () => request<Ticket[]>("/tickets"),
  ticket: (id: number) => request<TicketDetail>(`/tickets/${id}`),
  runTicket: (id: number, reset = false) => post<RunStatus>(`/tickets/${id}/run`, { reset }),
  run: (runId: string) => request<RunStatus>(`/runs/${encodeURIComponent(runId)}`),
  resolve: (id: number, resolved_by: string, note?: string) =>
    post<unknown>(`/tickets/${id}/resolve`, { resolved_by, note }),
  events: (params: { ticket_id?: number; since?: number; limit?: number; run_id?: string }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && q.set(k, String(v)));
    return request<EventsPage>(`/events?${q}`);
  },
  pending: () => request<{ count: number; requests: PaymentRequest[] }>("/payments/pending"),
  approve: (requestId: number, approved_by: string) =>
    post<{ ok: boolean; new_balance: number }>(`/payments/${requestId}/approve`, { approved_by }),
  reject: (requestId: number, rejected_by: string, reason: string) =>
    post<unknown>(`/payments/${requestId}/reject`, { rejected_by, reason }),
  metrics: () => request<Metrics>("/metrics"),
  setSpendLimit: (limit_usd: number) =>
    request<{ ok: boolean; spend_limit_usd: number }>("/settings/spend-limit", { method: "PUT", body: JSON.stringify({ limit_usd }) }),
  reset: () => post<{ ok: boolean }>("/reset"),
};

export const money = (n: number | null | undefined) =>
  n == null ? "-" : n.toLocaleString("en-US", { style: "currency", currency: "USD" });
