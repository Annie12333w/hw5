import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, money } from "./api";
import { playChime, unlockAudio } from "./chime";
import { buildRunView, eventsForRun, runIds } from "./runView";
import { ActivityLog } from "./components/ActivityLog";
import { AgentStage } from "./components/AgentStage";
import { MetricsBar } from "./components/MetricsBar";
import { SummaryPanel } from "./components/SummaryPanel";
import { TicketFacts } from "./components/TicketFacts";
import { STATUS_LABEL, TicketList } from "./components/TicketList";
import type { AgentEvent, Metrics, PaymentRequest, RunStatus, Ticket, TicketDetail } from "./types";

const DEFAULT_SUPERVISOR = "Supervisor #1";

type Toast = { kind: "ok" | "err" | "info"; text: string } | null;

function useStored<T>(key: string, initial: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    const raw = localStorage.getItem(key);
    return raw === null ? initial : (JSON.parse(raw) as T);
  });
  const set = (v: T) => { setValue(v); localStorage.setItem(key, JSON.stringify(v)); };
  return [value, set];
}

const errText = (e: unknown) => (e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e));

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [pending, setPending] = useState<PaymentRequest[]>([]);
  const [online, setOnline] = useState(true);
  // ?ticket=102 in the URL opens that ticket first (used for the resolved-board screenshots).
  const [selected, setSelected] = useState<number | null>(() => Number(new URLSearchParams(location.search).get("ticket")) || null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [pickedRun, setPickedRun] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<RunStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<Toast>(null);
  const [cashFlash, setCashFlash] = useState<"down" | null>(null);
  // Approvals are signed "Supervisor #1" unless the human types another name in the top bar.
  const [supervisor, setSupervisor] = useStored("cc-supervisor", DEFAULT_SUPERVISOR);
  const approver = supervisor.trim() || DEFAULT_SUPERVISOR;
  const [soundOn, setSoundOn] = useStored("cc-sound", true);

  const cursor = useRef<number | null>(null);
  const selectedRef = useRef<number | null>(null);
  const lastCash = useRef<number | null>(null);
  selectedRef.current = selected;

  const say = (kind: "ok" | "err" | "info", text: string) => {
    setToast({ kind, text });
    window.setTimeout(() => setToast((t) => (t?.text === text ? null : t)), 6000);
  };

  // ----- data loading -------------------------------------------------------------------

  const refreshBoard = useCallback(async () => {
    try {
      const [t, m, p] = await Promise.all([api.tickets(), api.metrics(), api.pending()]);
      setTickets(t);
      setMetrics(m);
      setPending(p.requests);
      setOnline(true);
      if (lastCash.current !== null && m.cash_balance < lastCash.current) {
        setCashFlash("down");
        window.setTimeout(() => setCashFlash(null), 2500);
      }
      lastCash.current = m.cash_balance;
      setSelected((s) => s ?? t[0]?.id ?? null);
      // Re-attach to a run that was started before this page loaded.
      if (m.active_run_id) setActiveRun((r) => r ?? { run_id: m.active_run_id!, ticket_id: m.active_ticket_id!, state: "running", started_utc: "", finished_utc: null, summary: null, error: null });
    } catch {
      setOnline(false);
    }
  }, []);

  const loadEvents = useCallback(async (full = false) => {
    const id = selectedRef.current;
    if (id == null) return;
    try {
      const since = full || cursor.current == null ? undefined : cursor.current;
      const page = await api.events({ ticket_id: id, since, limit: 500 });
      if (selectedRef.current !== id) return; // user switched tickets mid-request
      cursor.current = page.next_cursor;
      setEvents((prev) => {
        if (since === undefined) return page.events;
        const seen = new Set(prev.map((e) => e.cursor));
        return [...prev, ...page.events.filter((e) => !seen.has(e.cursor))];
      });
    } catch { /* board poll reports offline */ }
  }, []);

  const loadDetail = useCallback(async () => {
    const id = selectedRef.current;
    if (id == null) return;
    try { setDetail(await api.ticket(id)); } catch { setDetail(null); }
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshBoard(), loadEvents(), loadDetail()]);
  }, [refreshBoard, loadEvents, loadDetail]);

  const running = activeRun?.state === "running";

  useEffect(() => { void refreshBoard(); }, [refreshBoard]);
  useEffect(() => {
    const t = window.setInterval(() => void refreshBoard(), running ? 2000 : 5000);
    return () => window.clearInterval(t);
  }, [refreshBoard, running]);

  useEffect(() => {
    cursor.current = null;
    setEvents([]);
    setDetail(null);
    setPickedRun(null);
    void loadEvents(true);
    void loadDetail();
  }, [selected, loadEvents, loadDetail]);

  // Live updates while the team is working.
  useEffect(() => {
    if (!running || !activeRun) return;
    const t = window.setInterval(async () => {
      void loadEvents();
      try {
        const st = await api.run(activeRun.run_id);
        if (st.state !== "running") {
          setActiveRun(st);
          if (soundOn) playChime("done");
          if (st.state === "done") say("ok", `Ticket #${st.ticket_id}: the agents are done. Review the summary below.`);
          else say("err", `Run failed: ${st.error}`);
          void refreshAll();
        }
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) setActiveRun(null); // server restarted
      }
    }, 1000);
    return () => window.clearInterval(t);
  }, [running, activeRun, loadEvents, refreshAll, soundOn]);

  // ----- actions ------------------------------------------------------------------------

  const runTicket = async (id: number) => {
    unlockAudio();
    setBusy(true);
    try {
      const st = await api.runTicket(id);
      setActiveRun(st);
      setSelected(id);
      setPickedRun(null);
      say("info", `Agent team started on ticket #${id}. The Boss goes first.`);
      void refreshBoard();
    } catch (e) {
      say("err", errText(e));
    } finally {
      setBusy(false);
    }
  };

  const act = async (fn: () => Promise<string>) => {
    setBusy(true);
    try { say("ok", await fn()); } catch (e) { say("err", errText(e)); } finally {
      setBusy(false);
      void refreshAll();
    }
  };

  const approve = (req: PaymentRequest) => act(async () => {
    const r = await api.approve(req.id, approver);
    return `Paid ${money(req.amount)} to ${req.payee}. Checking is now ${money(r.new_balance)}.`;
  });
  const reject = (req: PaymentRequest, reason: string) => act(async () => {
    await api.reject(req.id, approver, reason);
    return `Rejected the ${money(req.amount)} request. No money moved.`;
  });
  const resolve = (note: string) => act(async () => {
    await api.resolve(selected!, approver, note || undefined);
    return `Ticket #${selected} marked resolved.`;
  });
  const setLimit = async (usd: number) => {
    try {
      const r = await api.setSpendLimit(usd);
      say("ok", `Spend limit set to $${r.spend_limit_usd.toFixed(2)}. The agents stop when spend since the last reset reaches it.`);
    } catch (e) {
      say("err", errText(e));
    } finally {
      void refreshBoard();
    }
  };
  const reset = () => {
    if (!window.confirm("Start over? This resets the shop data to the original database and clears the board: earlier runs, logs, payments, drafts and resolved statuses. The full history stays in the audit trail.")) return;
    void act(async () => {
      await api.reset();
      // Start a fresh session: hide earlier runs and logs (they stay in output/audit_trail.json).
      setActiveRun(null);
      cursor.current = null;
      setEvents([]);
      setPickedRun(null);
      setDetail(null);
      return "Shop data reset to the original values. Earlier runs are kept in the audit trail only.";
    });
  };

  // ----- derived view -------------------------------------------------------------------

  const ticket = tickets.find((t) => t.id === selected) ?? null;
  const runs = useMemo(() => runIds(events), [events]);
  const shownRun = pickedRun ?? runs[runs.length - 1] ?? null;
  const view = useMemo(() => buildRunView(events, shownRun), [events, shownRun]);
  const logEvents = useMemo(() => eventsForRun(events, shownRun), [events, shownRun]);
  const isLive = running && activeRun?.ticket_id === selected && (pickedRun === null || pickedRun === activeRun?.run_id);
  const ticketPending = pending.filter((p) => p.ticket_id === selected);
  const showSummary = !isLive && ticket && (view.finished || ticketPending.length > 0 || (detail?.drafts.length ?? 0) > 0
    || (detail?.payment_requests ?? []).some((r) => r.status === "paid"));

  return (
    <div className="app">
      <MetricsBar
        metrics={metrics} online={online} supervisor={supervisor} onSupervisor={setSupervisor}
        soundOn={soundOn} onToggleSound={() => { unlockAudio(); setSoundOn(!soundOn); }} cashFlash={cashFlash} onSetLimit={setLimit}
      />
      {!online && (
        <div className="banner err">
          Can't reach the backend at http://localhost:8000. Start it from the <code>backend</code> folder:{" "}
          <code>python -m uvicorn main:app --reload --port 8000</code>
        </div>
      )}

      <div className="layout">
        <TicketList
          tickets={tickets} selected={selected} runningTicket={running ? activeRun!.ticket_id : null}
          pending={pending} onSelect={setSelected} onRun={runTicket} onReset={reset}
          limitReached={!!metrics?.limit_reached}
        />

        <main className="workspace">
          {ticket ? (
            <>
              <div className="ws-head">
                <div>
                  <h1>#{ticket.id} · {ticket.subject}</h1>
                  <p className="muted">{ticket.requester}</p>
                </div>
                <div className="ws-head-right">
                  <span className={`badge status-${ticket.status}`}>{STATUS_LABEL[ticket.status] ?? ticket.status}</span>
                  {runs.length > 1 && (
                    <select value={shownRun ?? ""} onChange={(e) => setPickedRun(e.target.value)} aria-label="Choose run">
                      {runs.map((r, i) => (
                        <option key={r} value={r}>Run {i + 1}{i === runs.length - 1 ? " (latest)" : ""}</option>
                      ))}
                    </select>
                  )}
                  {isLive && <span className="live-tag"><span className="pulse-dot" /> Live</span>}
                </div>
              </div>

              <TicketFacts ticket={ticket} detail={detail} pending={ticketPending} />

              <AgentStage view={view} running={isLive} limitUsd={metrics?.spend_limit_usd ?? 3} />
              <ActivityLog events={logEvents} running={isLive} />

              {showSummary ? (
                <SummaryPanel
                  ticket={ticket} view={view} detail={detail} pending={ticketPending}
                  cash={metrics?.cash_balance ?? null} supervisor={approver} busy={busy}
                  onApprove={approve} onReject={reject} onResolve={resolve} onRerun={() => runTicket(ticket.id)}
                />
              ) : (
                !isLive && runs.length === 0 && (
                  <div className="hint">
                    Press <b>▶ Run agent team</b> on the ticket to start. The Boss reads it and calls only the specialists it needs.
                  </div>
                )
              )}
            </>
          ) : (
            <div className="hint">Loading tickets…</div>
          )}
        </main>
      </div>

      {toast && <div className={`toast ${toast.kind}`} role="status">{toast.text}</div>}
    </div>
  );
}
