"""Campus Customs MCP server.

Gives the Campus Customs agent team (Boss, Inventory, Accounting, Facilities,
Customer Service) tools over the shop's working database,
data/campus_customs_new.db. The original data/campus_customs.db is never opened.

Every tool returns only values stored in the database. "Today" is always
desk.date_today, never the system clock. If a row is missing, the tool says so
instead of guessing.

Tool groups:
- Read tools (shop facts): check_stock, check_vendor_invoices, get_lease_status,
  get_shop_date, list_tickets, get_ticket, get_cash_balance, check_price_margin,
  list_payments, list_payment_requests.
- Agent write tools (no money moves): update_ticket, save_draft,
  draft_purchase_order, request_payment.
- HUMAN-ONLY tools (never given to agents): approve_payment, reject_payment.
  approve_payment is the only code path that moves cash.

Drafts are stored in output/drafts.json and are never sent. Payment requests
wait in data/payment_requests.json until a human approves or rejects them.

Run: python server.py   # stdio transport
"""

import calendar
import json
import os
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

try:
    from fastmcp import FastMCP
except ImportError:
    # mcp 2.x ships FastMCP under its new name, MCPServer (same decorator API).
    from mcp.server.mcpserver import MCPServer as FastMCP

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"
ORIGINAL_DB = DATA_DIR / "campus_customs.db"
DB_PATH = Path(os.getenv("CAMPUS_DB_PATH", DATA_DIR / "campus_customs_new.db")).resolve()

DRAFTS_PATH = Path(os.getenv("CAMPUS_DRAFTS_PATH", HERE.parent / "output" / "drafts.json")).resolve()
REQUESTS_PATH = Path(os.getenv("CAMPUS_REQUESTS_PATH", DATA_DIR / "payment_requests.json")).resolve()
# Stock that a vendor will now deliver because a human approved the payment (invoice or PO).
# Kept apart from inventory.qty: goods are not on the shelf until they arrive (today + lead_days).
INCOMING_PATH = Path(os.getenv("CAMPUS_INCOMING_PATH", DATA_DIR / "incoming_stock.json")).resolve()

TICKET_STATUSES = ("open", "in_progress", "waiting_approval", "blocked", "resolved")
DRAFT_KINDS = ("customer_message", "vendor_message", "landlord_message")
PAYMENT_KINDS = ("invoice", "rent", "purchase_order")
AGENT_NAMES = ("boss", "inventory", "accounting", "facilities", "customer_service")
UPCOMING_DAYS = 7  # rent due within this many days counts as an upcoming obligation
MAX_NOTE_CHARS = 600
MAX_BODY_CHARS = 2000

if DB_PATH == ORIGINAL_DB.resolve():
    raise RuntimeError("Refusing to use the original campus_customs.db; point at campus_customs_new.db.")

mcp = FastMCP(
    "campus-customs",
    instructions=(
        "Tools for the Campus Customs operations team. All data comes from "
        "campus_customs_new.db. Use desk.date_today as today. Never invent values."
    ),
)


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _today(conn: sqlite3.Connection) -> date:
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    if row is None:
        raise RuntimeError("desk.date_today is missing from the database.")
    return date.fromisoformat(row["date_today"])


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_list(path: Path) -> list:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8") or "[]")


def _save_list(path: Path, items: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(items, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _next_id(items: list) -> int:
    return max((i["id"] for i in items), default=0) + 1


def _add_one_month(d: date) -> date:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _append_ticket_note(conn: sqlite3.Connection, ticket_id: int, today: date, who: str, note: str) -> None:
    row = conn.execute("SELECT notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if row is None:
        return
    entry = f"[{today.isoformat()} {who}] {note.strip()[:MAX_NOTE_CHARS]}"
    notes = f"{row['notes']}\n{entry}" if row["notes"] else entry
    conn.execute("UPDATE tickets SET notes = ? WHERE id = ?", (notes, ticket_id))


def _pending_requests() -> list:
    return [r for r in _load_list(REQUESTS_PATH) if r["status"] == "pending_approval"]


def _incoming_for(sku: str, size: str | None = None) -> list:
    return [i for i in _load_list(INCOMING_PATH) if i["sku"] == sku and (size is None or i["size"] == size)]


def _invoice_items(conn: sqlite3.Connection, description: str | None) -> list[dict]:
    """Inventory rows (sku + size) named in an invoice description, e.g. 'Rush reprint CC-TEE-WHITE S'.
    Only exact matches against real inventory rows count; the description holds no quantity."""
    if not description:
        return []
    found = []
    for r in conn.execute("SELECT sku, size, name FROM inventory"):
        if re.search(rf"(?<![\w-]){re.escape(r['sku'])}\s+{re.escape(r['size'])}(?!\w)", description):
            found.append(dict(r))
    return found


@mcp.tool()
def check_stock(sku: str, size: str | None = None, requested_qty: int | None = None) -> dict:
    """Check units on hand for a SKU (optionally one size) in the inventory table.

    Pass requested_qty to get the shortfall (requested minus on hand, never below 0).
    Used by Inventory for ticket 101 (CC-TEE-WHITE size S) and ticket 103
    (CC-HOOD-NAVY size M, 20 units).
    """
    with _connect() as conn:
        query = "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ?"
        params: list = [sku]
        if size:
            query += " AND size = ?"
            params.append(size)
        rows = [dict(r) for r in conn.execute(query, params)]

    if not rows:
        return {"found": False, "sku": sku, "size": size,
                "message": "No matching row in inventory for this SKU/size."}

    result: dict = {"found": True, "sku": sku, "size": size, "rows": rows,
                    "total_on_hand": sum(r["qty"] for r in rows)}
    if requested_qty is not None:
        result["requested_qty"] = requested_qty
        result["shortfall"] = max(0, requested_qty - result["total_on_hand"])
        result["can_fill_from_stock"] = result["shortfall"] == 0
    # Approved deliveries that are on their way (not yet on the shelf).
    incoming = _incoming_for(sku, size)
    result["incoming"] = incoming
    if incoming:
        result["incoming_note"] = ("On order and not yet on the shelf; on-hand numbers exclude these. "
                                   "qty null means the quantity was not recorded.")
    return result


@mcp.tool()
def check_vendor_invoices(vendor_id: int | None = None, invoice_id: int | None = None) -> dict:
    """Show a vendor's lead time and open invoices, and whether the vendor will ship.

    Look up by vendor_id, or by invoice_id (resolves to that invoice's vendor).
    With neither, returns every vendor so Inventory can pick one by specialty.
    A vendor with any open invoice will not ship new product. Days overdue are
    measured from desk.date_today. Unlocks ticket 101 (invoice 501 blocks the tee
    reprint) and ticket 103 (a hoodie reorder goes to the same apparel vendor).
    """
    with _connect() as conn:
        today = _today(conn)

        if invoice_id is not None:
            inv = conn.execute("SELECT vendor_id FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
            if inv is None:
                return {"found": False, "invoice_id": invoice_id,
                        "message": "No invoice with this id."}
            vendor_id = inv["vendor_id"]

        if vendor_id is not None:
            vendors = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchall()
            if not vendors:
                return {"found": False, "vendor_id": vendor_id,
                        "message": "No vendor with this id."}
        else:
            vendors = conn.execute("SELECT * FROM vendors ORDER BY id").fetchall()

        out = []
        for v in vendors:
            open_invoices = []
            for inv in conn.execute(
                "SELECT id, amount, due_date, status, description FROM invoices "
                "WHERE vendor_id = ? AND status = 'open' ORDER BY due_date", (v["id"],)
            ):
                days_past_due = (today - date.fromisoformat(inv["due_date"])).days
                open_invoices.append({**dict(inv),
                                      "days_overdue": max(0, days_past_due),
                                      "is_overdue": days_past_due > 0})
            out.append({
                **dict(v),
                "open_invoices": open_invoices,
                "open_balance": sum(i["amount"] for i in open_invoices),
                "will_ship_new_product": not open_invoices,
            })

    return {"found": True, "date_today": today.isoformat(), "vendors": out}


@mcp.tool()
def get_lease_status(lease_id: int) -> dict:
    """Show a lease's landlord, monthly rent, and next due date from the leases table.

    Days until due are measured from desk.date_today (negative means overdue).
    Used by Facilities for ticket 102 (Chapel Street shop rent notice).
    """
    with _connect() as conn:
        today = _today(conn)
        lease = conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchone()

    if lease is None:
        return {"found": False, "lease_id": lease_id, "message": "No lease with this id."}

    days_until_due = (date.fromisoformat(lease["next_due"]) - today).days
    return {
        "found": True,
        **dict(lease),
        "date_today": today.isoformat(),
        "days_until_due": days_until_due,
        "is_overdue": days_until_due < 0,
    }


# ---------------------------------------------------------------------------
# Read tools added in Problem 5
# ---------------------------------------------------------------------------

@mcp.tool()
def get_shop_date() -> dict:
    """Return the shop's "today" (desk.date_today) and desk notes.

    Every agent uses this date, never the real clock, for overdue checks,
    days-until-due and vendor arrival dates (today + vendors.lead_days).
    """
    with _connect() as conn:
        row = conn.execute("SELECT date_today, notes FROM desk LIMIT 1").fetchone()
    return {"found": row is not None, **(dict(row) if row else {})}


@mcp.tool()
def list_tickets(status: str | None = None) -> dict:
    """List tickets on the board (tickets table), optionally filtered by status.

    Status values: open, in_progress, waiting_approval, blocked, resolved.
    The Boss uses this to see the whole board and set priorities.
    """
    with _connect() as conn:
        if status:
            rows = conn.execute("SELECT * FROM tickets WHERE status = ? ORDER BY id", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()
    return {"count": len(rows), "tickets": [dict(r) for r in rows]}


@mcp.tool()
def get_ticket(ticket_id: int) -> dict:
    """Return one ticket plus every row it links to.

    Follows tickets.invoice_id -> invoices -> vendors, tickets.lease_id -> leases,
    and tickets.sku/size -> inventory and pricing. Also lists drafts and payment
    requests already filed for this ticket. This is the Boss's starting point.
    """
    with _connect() as conn:
        t = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"found": False, "ticket_id": ticket_id, "message": "No ticket with this id."}
        out: dict = {"found": True, "date_today": _today(conn).isoformat(), "ticket": dict(t)}
        if t["invoice_id"] is not None:
            inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (t["invoice_id"],)).fetchone()
            out["invoice"] = dict(inv) if inv else None
            if inv:
                v = conn.execute("SELECT * FROM vendors WHERE id = ?", (inv["vendor_id"],)).fetchone()
                out["invoice_vendor"] = dict(v) if v else None
        if t["lease_id"] is not None:
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (t["lease_id"],)).fetchone()
            out["lease"] = dict(lease) if lease else None
        if t["sku"]:
            if t["size"]:
                rows = conn.execute("SELECT * FROM inventory WHERE sku = ? AND size = ?", (t["sku"], t["size"]))
            else:
                rows = conn.execute("SELECT * FROM inventory WHERE sku = ?", (t["sku"],))
            out["inventory"] = [dict(r) for r in rows]
            out["incoming"] = _incoming_for(t["sku"], t["size"])
            p = conn.execute("SELECT * FROM pricing WHERE sku = ?", (t["sku"],)).fetchone()
            out["pricing"] = dict(p) if p else None
    out["drafts"] = [d for d in _load_list(DRAFTS_PATH) if d.get("ticket_id") == ticket_id]
    out["payment_requests"] = [r for r in _load_list(REQUESTS_PATH) if r.get("ticket_id") == ticket_id]
    return out


@mcp.tool()
def get_cash_balance(account: str = "checking") -> dict:
    """Return a cash account's balance (cash_accounts) and what is already committed.

    available_after_pending = balance minus every payment request still waiting
    for human approval. upcoming_unqueued_bills lists open invoices and rent due
    within 7 days that nobody has queued yet; available_after_upcoming subtracts
    them too, and is the number to use before any discretionary spend (like a PO).
    Cash only goes out (no revenue is modeled).
    """
    with _connect() as conn:
        row = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if row is None:
            return {"found": False, "account": account, "message": "No cash account with this name."}
        today = _today(conn)
        pending = [r for r in _pending_requests() if r["account"] == account]
        queued = {(r["kind"], r["ref_id"]) for r in pending}
        # Bills that will need this cash soon but are not queued yet, so tickets worked one after
        # another don't spend money another ticket needs (e.g. a PO using up next week's rent).
        upcoming = []
        for inv in conn.execute("SELECT i.*, v.name AS vendor FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
                                "WHERE i.status = 'open'"):
            if ("invoice", inv["id"]) not in queued:
                upcoming.append({"kind": "invoice", "ref_id": inv["id"], "payee": inv["vendor"],
                                 "amount": inv["amount"], "due": inv["due_date"]})
        for lease in conn.execute("SELECT * FROM leases"):
            days = (date.fromisoformat(lease["next_due"]) - today).days
            if days <= UPCOMING_DAYS and ("rent", lease["id"]) not in queued:
                upcoming.append({"kind": "rent", "ref_id": lease["id"], "payee": lease["landlord"],
                                 "amount": lease["monthly_rent"], "due": lease["next_due"]})
    committed = round(sum(r["amount"] for r in pending), 2)
    upcoming_total = round(sum(u["amount"] for u in upcoming), 2)
    return {"found": True, **dict(row), "pending_requests": len(pending),
            "pending_total": committed,
            "available_after_pending": round(row["balance"] - committed, 2),
            "upcoming_unqueued_bills": upcoming,
            "available_after_upcoming": round(row["balance"] - committed - upcoming_total, 2),
            "upcoming_window_days": UPCOMING_DAYS}


@mcp.tool()
def check_price_margin(sku: str, proposed_unit_price: float | None = None, qty: int | None = None) -> dict:
    """Return unit_cost, list_price and margin for a SKU (pricing table).

    Pass proposed_unit_price to test a discount: returns the discount percent,
    the margin at that price, and below_cost (true means the price is under
    unit_cost and must not be offered). Pass qty for order totals.
    """
    with _connect() as conn:
        p = conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if p is None:
        return {"found": False, "sku": sku, "message": "No pricing row for this SKU."}
    cost, lst = p["unit_cost"], p["list_price"]
    out: dict = {"found": True, **dict(p),
                 "list_margin_per_unit": round(lst - cost, 2),
                 "list_margin_pct": round((lst - cost) / lst * 100, 1)}
    if proposed_unit_price is not None:
        price = proposed_unit_price
        out.update({
            "proposed_unit_price": price,
            "discount_pct_vs_list": round((lst - price) / lst * 100, 1),
            "margin_per_unit": round(price - cost, 2),
            "margin_pct": round((price - cost) / price * 100, 1) if price else None,
            "below_cost": price < cost,
        })
    if qty is not None:
        unit = proposed_unit_price if proposed_unit_price is not None else lst
        out.update({"qty": qty, "order_revenue": round(unit * qty, 2),
                    "order_cost": round(cost * qty, 2),
                    "order_margin": round((unit - cost) * qty, 2)})
    return out


@mcp.tool()
def list_payments(kind: str | None = None, ref_id: int | None = None) -> dict:
    """List payments already made (payments ledger), optionally by kind and ref_id.

    Use before requesting a payment so the same bill is never paid twice.
    """
    query, params = "SELECT * FROM payments WHERE 1=1", []
    if kind:
        query += " AND kind = ?"
        params.append(kind)
    if ref_id is not None:
        query += " AND ref_id = ?"
        params.append(ref_id)
    with _connect() as conn:
        rows = [dict(r) for r in conn.execute(query + " ORDER BY id", params)]
    return {"count": len(rows), "total": round(sum(r["amount"] for r in rows), 2), "payments": rows}


@mcp.tool()
def list_payment_requests(status: str | None = None) -> dict:
    """List payment requests waiting for (or decided by) the human supervisor.

    Status values: pending_approval, paid, rejected, refused.
    """
    reqs = _load_list(REQUESTS_PATH)
    if status:
        reqs = [r for r in reqs if r["status"] == status]
    return {"count": len(reqs), "requests": reqs}


# ---------------------------------------------------------------------------
# Agent write tools (no money moves)
# ---------------------------------------------------------------------------

@mcp.tool()
def update_ticket(ticket_id: int, agent: str, status: str | None = None, note: str | None = None) -> dict:
    """Change a ticket's status and/or append a dated note (tickets table).

    Notes are appended, never overwritten, and stamped with desk.date_today and
    the agent name. Only the Boss or the human supervisor (agent='human', set by
    the dashboard's resolve route; the backend never lets an agent claim it) may
    set status 'resolved', and not while the ticket still has a payment request
    waiting for human approval.
    """
    if status is not None and status not in TICKET_STATUSES:
        return {"ok": False, "message": f"status must be one of {TICKET_STATUSES}."}
    if status is None and not note:
        return {"ok": False, "message": "Nothing to update: pass status and/or note."}
    if status == "resolved":
        if agent not in ("boss", "human"):
            return {"ok": False, "message": "Only the Boss or the human supervisor can resolve a ticket."}
        if any(r["ticket_id"] == ticket_id for r in _pending_requests()):
            return {"ok": False, "message": "Ticket has a payment request pending human approval; cannot resolve yet."}
    with _connect() as conn:
        t = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"ok": False, "message": "No ticket with this id."}
        today = _today(conn)
        if status is not None:
            conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        if note:
            _append_ticket_note(conn, ticket_id, today, agent, note)
        row = dict(conn.execute("SELECT id, status, notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone())
    return {"ok": True, "previous_status": t["status"], "ticket": row}


@mcp.tool()
def save_draft(ticket_id: int, kind: str, subject: str, body: str, agent: str,
               vendor_id: int | None = None, lease_id: int | None = None,
               run_id: str | None = None) -> dict:
    """Save a message DRAFT for human review. Nothing is ever sent.

    kind: customer_message (recipient = the ticket's requester),
    vendor_message (needs vendor_id; recipient = vendors.name), or
    landlord_message (needs lease_id; recipient = leases.landlord).
    The recipient is always looked up from the database, never typed by an agent.
    """
    if kind not in DRAFT_KINDS:
        return {"ok": False, "message": f"kind must be one of {DRAFT_KINDS}."}
    if len(body) > MAX_BODY_CHARS:
        return {"ok": False, "message": f"Body is over {MAX_BODY_CHARS} characters; shorten it."}
    with _connect() as conn:
        today = _today(conn)
        t = conn.execute("SELECT requester FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"ok": False, "message": "No ticket with this id."}
        if kind == "customer_message":
            recipient = t["requester"]
        elif kind == "vendor_message":
            v = conn.execute("SELECT name FROM vendors WHERE id = ?", (vendor_id,)).fetchone() if vendor_id else None
            if v is None:
                return {"ok": False, "message": "vendor_message needs a valid vendor_id."}
            recipient = v["name"]
        else:
            lease = conn.execute("SELECT landlord FROM leases WHERE id = ?", (lease_id,)).fetchone() if lease_id else None
            if lease is None:
                return {"ok": False, "message": "landlord_message needs a valid lease_id."}
            recipient = lease["landlord"]
    drafts = _load_list(DRAFTS_PATH)
    draft = {"id": _next_id(drafts), "ticket_id": ticket_id, "kind": kind, "recipient": recipient,
             "subject": subject, "body": body, "author_agent": agent, "run_id": run_id,
             "shop_date": today.isoformat(), "created_at_utc": _now_utc(),
             "status": "draft_not_sent"}
    drafts.append(draft)
    _save_list(DRAFTS_PATH, drafts)
    return {"ok": True, "draft": draft, "message": "Saved as a draft for human review. Not sent."}


@mcp.tool()
def draft_purchase_order(ticket_id: int, sku: str, size: str, qty: int, vendor_id: int,
                         agent: str, run_id: str | None = None) -> dict:
    """Draft a purchase order (PO) for human review. No money moves, nothing is sent.

    Prices the PO from pricing.unit_cost x qty, sets the expected arrival to
    desk.date_today + vendors.lead_days, and flags whether the vendor will ship
    (not while it has an open invoice) and whether cash covers it.
    """
    if qty <= 0:
        return {"ok": False, "message": "qty must be positive."}
    with _connect() as conn:
        today = _today(conn)
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            return {"ok": False, "message": "No ticket with this id."}
        if conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone() is None:
            return {"ok": False, "message": "No inventory row for this SKU/size."}
        p = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if p is None:
            return {"ok": False, "message": "No pricing row for this SKU."}
        v = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if v is None:
            return {"ok": False, "message": "No vendor with this id."}
        open_inv = [dict(r) for r in conn.execute(
            "SELECT id, amount, due_date FROM invoices WHERE vendor_id = ? AND status = 'open'", (vendor_id,))]
        cash = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()
    total = round(p["unit_cost"] * qty, 2)
    available = round(cash["balance"] - sum(r["amount"] for r in _pending_requests()), 2) if cash else 0.0
    drafts = _load_list(DRAFTS_PATH)
    po = {"id": _next_id(drafts), "ticket_id": ticket_id, "kind": "purchase_order",
          "recipient": v["name"], "vendor_id": vendor_id, "vendor_specialty": v["specialty"],
          "sku": sku, "size": size, "qty": qty, "unit_cost": p["unit_cost"], "total": total,
          "lead_days": v["lead_days"],
          "expected_arrival_if_ordered_today": date.fromordinal(today.toordinal() + v["lead_days"]).isoformat(),
          "vendor_will_ship": not open_inv, "blocking_invoices": open_inv,
          "cash_available_after_pending": available, "cash_covers_total": total <= available,
          "author_agent": agent, "run_id": run_id, "shop_date": today.isoformat(),
          "created_at_utc": _now_utc(), "status": "draft_not_sent"}
    drafts.append(po)
    _save_list(DRAFTS_PATH, drafts)
    return {"ok": True, "purchase_order": po,
            "message": "PO saved as a draft. To pay it, Accounting must call request_payment"
                       "(kind='purchase_order', ref_id=<this id>) and a human must approve."}


@mcp.tool()
def request_payment(kind: str, ref_id: int, amount: float, ticket_id: int, reason: str,
                    agent: str, account: str = "checking", run_id: str | None = None) -> dict:
    """Queue a payment for HUMAN approval. This does NOT move money.

    kind 'invoice' (ref_id = invoices.id, amount must equal the open invoice),
    'rent' (ref_id = leases.id, amount must equal monthly_rent), or
    'purchase_order' (ref_id = PO draft id, amount must equal its total, and the
    vendor must have no open invoice). Refused if the amount is more than the cash
    left after other pending requests, or if the same item is already queued or paid.
    """
    if kind not in PAYMENT_KINDS:
        return {"ok": False, "message": f"kind must be one of {PAYMENT_KINDS}."}
    with _connect() as conn:
        today = _today(conn)
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            return {"ok": False, "message": "No ticket with this id."}
        if kind == "invoice":
            row = conn.execute("SELECT * FROM invoices WHERE id = ?", (ref_id,)).fetchone()
            if row is None:
                return {"ok": False, "message": "No invoice with this id."}
            if row["status"] != "open":
                return {"ok": False, "message": f"Invoice is '{row['status']}', not open."}
            expected = row["amount"]
            payee = conn.execute("SELECT name FROM vendors WHERE id = ?", (row["vendor_id"],)).fetchone()["name"]
        elif kind == "rent":
            row = conn.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if row is None:
                return {"ok": False, "message": "No lease with this id."}
            expected, payee = row["monthly_rent"], row["landlord"]
        else:
            po = next((d for d in _load_list(DRAFTS_PATH)
                       if d["id"] == ref_id and d["kind"] == "purchase_order"), None)
            if po is None:
                return {"ok": False, "message": "No purchase-order draft with this id."}
            if po["status"] == "approved_paid":
                return {"ok": False, "message": "This PO has already been paid."}
            if conn.execute("SELECT 1 FROM invoices WHERE vendor_id = ? AND status = 'open'",
                            (po["vendor_id"],)).fetchone():
                return {"ok": False, "refused": True,
                        "message": f"{po['recipient']} has an open invoice and will not ship; that invoice must be paid first."}
            expected, payee = po["total"], po["recipient"]
        cash = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
    if cash is None:
        return {"ok": False, "message": "No cash account with this name."}
    if round(amount, 2) != round(expected, 2):
        return {"ok": False, "message": f"Amount {amount} does not match the database amount {expected}."}
    pending = _pending_requests()
    if any(r["kind"] == kind and r["ref_id"] == ref_id for r in pending):
        return {"ok": False, "message": "A request for this item is already waiting for approval."}
    available = round(cash["balance"] - sum(r["amount"] for r in pending if r["account"] == account), 2)
    if amount > available:
        return {"ok": False, "refused": True,
                "message": f"Refused: {amount:.2f} is more than the {available:.2f} left after pending requests.",
                "balance": cash["balance"], "available_after_pending": available}
    reqs = _load_list(REQUESTS_PATH)
    req = {"id": _next_id(reqs), "kind": kind, "ref_id": ref_id, "amount": round(amount, 2),
           "payee": payee, "account": account, "ticket_id": ticket_id, "reason": reason[:MAX_NOTE_CHARS],
           "requested_by": agent, "run_id": run_id, "shop_date": today.isoformat(),
           "created_at_utc": _now_utc(), "status": "pending_approval"}
    reqs.append(req)
    _save_list(REQUESTS_PATH, reqs)
    return {"ok": True, "request": req, "available_after_this_request": round(available - amount, 2),
            "message": "Queued for human approval. No money has moved."}


# ---------------------------------------------------------------------------
# HUMAN-ONLY tools. The backend never gives these to an agent.
# ---------------------------------------------------------------------------

@mcp.tool()
def approve_payment(request_id: int, approved_by: str) -> dict:
    """HUMAN ONLY. Approve a queued payment and pay it in one transaction.

    Refuses if cash is short. On success: lowers cash_accounts.balance, inserts
    a payments row (approved_by = the human), and updates the related row
    (invoice -> status 'paid'; rent -> leases.next_due moves one month; PO ->
    draft marked paid). Also notes the payment on the linked ticket.
    """
    approver = (approved_by or "").strip()
    if not approver or approver.lower() in AGENT_NAMES + ("agent", "system", "human"):
        return {"ok": False, "message": "approved_by must be the name of a human supervisor."}
    reqs = _load_list(REQUESTS_PATH)
    req = next((r for r in reqs if r["id"] == request_id), None)
    if req is None:
        return {"ok": False, "message": "No payment request with this id."}
    if req["status"] != "pending_approval":
        return {"ok": False, "message": f"Request is '{req['status']}', not pending."}
    drafts = _load_list(DRAFTS_PATH)
    new_incoming: list[dict] = []
    with _connect() as conn:
        today = _today(conn)
        cash = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (req["account"],)).fetchone()
        if cash is None or req["amount"] > cash["balance"]:
            req.update(status="refused", decided_by=approver, decided_at_utc=_now_utc(),
                       decision_note="Refused by pay tool: not enough cash.")
            _save_list(REQUESTS_PATH, reqs)
            return {"ok": False, "refused": True, "message": "Refused: not enough cash.",
                    "balance": cash["balance"] if cash else None, "amount": req["amount"]}
        if req["kind"] == "invoice":
            inv = conn.execute("SELECT status FROM invoices WHERE id = ?", (req["ref_id"],)).fetchone()
            if inv is None or inv["status"] != "open":
                return {"ok": False, "message": "Invoice is no longer open."}
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (req["ref_id"],))
            related = {"table": "invoices", "id": req["ref_id"], "status": "paid"}
            linked = [r["id"] for r in conn.execute("SELECT id FROM tickets WHERE invoice_id = ?", (req["ref_id"],))]
            # Paying the bill releases the goods it covers: record them as incoming from the vendor.
            inv_row = conn.execute("SELECT * FROM invoices WHERE id = ?", (req["ref_id"],)).fetchone()
            vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (inv_row["vendor_id"],)).fetchone()
            for item in _invoice_items(conn, inv_row["description"]):
                new_incoming.append({
                    "sku": item["sku"], "size": item["size"], "name": item["name"], "qty": None,
                    "vendor_id": vendor["id"], "vendor": vendor["name"], "lead_days": vendor["lead_days"],
                    "expected_arrival": date.fromordinal(today.toordinal() + vendor["lead_days"]).isoformat(),
                    "source": f"invoice #{req['ref_id']} paid ({inv_row['description']})",
                    "note": "Quantity is not recorded on the invoice."})
            still_open = conn.execute("SELECT COUNT(*) FROM invoices WHERE vendor_id = ? AND status = 'open'",
                                      (vendor["id"],)).fetchone()[0]
            related["vendor_will_ship_new_product"] = still_open == 0
        elif req["kind"] == "rent":
            lease = conn.execute("SELECT next_due FROM leases WHERE id = ?", (req["ref_id"],)).fetchone()
            new_due = _add_one_month(date.fromisoformat(lease["next_due"])).isoformat()
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (new_due, req["ref_id"]))
            related = {"table": "leases", "id": req["ref_id"],
                       "previous_next_due": lease["next_due"], "next_due": new_due}
            linked = [r["id"] for r in conn.execute("SELECT id FROM tickets WHERE lease_id = ?", (req["ref_id"],))]
        else:
            po = next(d for d in drafts if d["id"] == req["ref_id"])
            po.update(status="approved_paid", paid_at=today.isoformat())
            related = {"file": "output/drafts.json", "purchase_order_id": po["id"], "status": "approved_paid"}
            linked = [req["ticket_id"]]
            new_incoming.append({
                "sku": po["sku"], "size": po["size"], "name": None, "qty": po["qty"],
                "vendor_id": po["vendor_id"], "vendor": po["recipient"], "lead_days": po["lead_days"],
                "expected_arrival": date.fromordinal(today.toordinal() + po["lead_days"]).isoformat(),
                "source": f"purchase order #{po['id']} paid", "note": None})
        conn.execute("UPDATE cash_accounts SET balance = balance - ?, date = ? WHERE name = ?",
                     (req["amount"], today.isoformat(), req["account"]))
        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?,?,?,?,?,?)",
            (req["kind"], req["ref_id"], req["amount"], req["account"], today.isoformat(), approver))
        payment_id = cur.lastrowid
        for tid in linked:
            _append_ticket_note(conn, tid, today, "human",
                                f"Payment #{payment_id} of {req['amount']:.2f} ({req['kind']} {req['ref_id']}) "
                                f"approved by {approver}.")
        new_balance = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?",
                                   (req["account"],)).fetchone()["balance"]
    if req["kind"] == "purchase_order":
        _save_list(DRAFTS_PATH, drafts)
    if new_incoming:
        incoming = _load_list(INCOMING_PATH)
        for item in new_incoming:
            incoming.append({"id": _next_id(incoming), "payment_id": payment_id, "status": "on_order",
                             "ordered_on": today.isoformat(), **item})
        _save_list(INCOMING_PATH, incoming)
    req.update(status="paid", decided_by=approver, decided_at_utc=_now_utc(), payment_id=payment_id)
    _save_list(REQUESTS_PATH, reqs)
    return {"ok": True, "payment_id": payment_id, "amount": req["amount"], "new_balance": new_balance,
            "related_update": related, "incoming_stock": new_incoming, "request": req}


@mcp.tool()
def reject_payment(request_id: int, rejected_by: str, reason: str) -> dict:
    """HUMAN ONLY. Reject a queued payment. No money moves."""
    reqs = _load_list(REQUESTS_PATH)
    req = next((r for r in reqs if r["id"] == request_id), None)
    if req is None or req["status"] != "pending_approval":
        return {"ok": False, "message": "No pending payment request with this id."}
    req.update(status="rejected", decided_by=(rejected_by or "").strip(),
               decided_at_utc=_now_utc(), decision_note=reason)
    _save_list(REQUESTS_PATH, reqs)
    return {"ok": True, "request": req}


if __name__ == "__main__":
    mcp.run()
