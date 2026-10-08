"""Plain-English narration of agent steps for the dashboard.

Turns tool calls and their MCP results into sentences a supervisor can read, e.g.
  check_stock {"sku": "CC-TEE-WHITE", "size": "S", "requested_qty": 1}
  -> "Checking the shelf for CC-TEE-WHITE in size S (need 1). Found 0 on hand, 1 short."
Every value shown comes from the tool's arguments or its database result.
"""

from typing import Any

AGENT_TITLES = {"boss": "the Boss", "inventory": "Inventory", "accounting": "Accounting",
                "facilities": "Facilities", "customer_service": "Customer Service"}
STATUS_WORDS = {"open": "open", "in_progress": "in progress", "waiting_approval": "waiting for your approval",
                "blocked": "blocked", "resolved": "resolved"}
KIND_WORDS = {"invoice": "vendor invoice", "rent": "rent", "purchase_order": "purchase order",
              "customer_message": "customer message", "vendor_message": "vendor message",
              "landlord_message": "landlord message"}


def _usd(x: Any) -> str:
    try:
        return f"${float(x):,.2f}"
    except (TypeError, ValueError):
        return str(x)


def _first_sentence(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def describe_call(tool: str, a: dict | None) -> str:
    a = a if isinstance(a, dict) else {}
    g = a.get
    if tool == "check_stock":
        what = f"{g('sku')}" + (f" in size {g('size')}" if g("size") else "")
        return f"Checking the shelf for {what}" + (f" (need {g('requested_qty')})" if g("requested_qty") is not None else "")
    if tool == "check_vendor_invoices":
        if g("invoice_id") is not None:
            return f"Looking up invoice #{g('invoice_id')} and whether that vendor will ship"
        if g("vendor_id") is not None:
            return f"Checking vendor #{g('vendor_id')}'s open bills and lead time"
        return "Reviewing the vendor list"
    if tool == "get_lease_status":
        return f"Checking lease #{g('lease_id')}: rent and due date"
    if tool == "get_shop_date":
        return "Checking today's shop date"
    if tool == "list_tickets":
        return "Reviewing the ticket board"
    if tool == "get_ticket":
        return f"Reading ticket #{g('ticket_id')} and everything linked to it"
    if tool == "get_cash_balance":
        return "Checking the bank balance"
    if tool == "check_price_margin":
        if g("proposed_unit_price") is not None:
            return f"Testing a price of {_usd(g('proposed_unit_price'))} each for {g('sku')}" + (
                f" on {g('qty')} units" if g("qty") else "")
        return f"Looking up cost and list price for {g('sku')}"
    if tool == "list_payments":
        return "Checking past payments so nothing is paid twice"
    if tool == "list_payment_requests":
        return "Checking which payments are already waiting for approval"
    if tool == "update_ticket":
        parts = []
        if g("status"):
            parts.append(f"marking ticket #{g('ticket_id')} as {STATUS_WORDS.get(g('status'), g('status'))}")
        if g("note"):
            parts.append(f"adding a note: “{_first_sentence(g('note'), 120)}”")
        return ("Updating the ticket: " + " and ".join(parts)) if parts else "Updating the ticket"
    if tool == "save_draft":
        return f"Writing a {KIND_WORDS.get(g('kind'), 'message')} draft: “{g('subject', '')}” (not sent)"
    if tool == "draft_purchase_order":
        return f"Drafting a purchase order for {g('qty')} × {g('sku')} size {g('size')} from vendor #{g('vendor_id')}"
    if tool == "request_payment":
        return (f"Asking you to approve {_usd(g('amount'))} for {KIND_WORDS.get(g('kind'), g('kind'))} "
                f"#{g('ref_id')}")
    if tool == "delegate":
        who = AGENT_TITLES.get(g("to_agent"), g("to_agent"))
        return f"Handing off to {who}: {_first_sentence(g('task', ''), 140)}"
    if tool == "finish":
        return "Writing up the final report"
    if tool == "approve_payment":
        return f"Approving payment request #{g('request_id')}"
    if tool == "reject_payment":
        return f"Rejecting payment request #{g('request_id')}"
    return f"Using {tool.replace('_', ' ')}"


def describe_result(tool: str, r: Any) -> str:
    if not isinstance(r, dict):
        return ""
    if r.get("blocked_by_guardrail"):
        return f"Blocked by a safety rule: {r.get('message')}"
    if r.get("ok") is False or r.get("found") is False:
        return f"Not done: {r.get('message', 'no matching record')}"
    if tool == "check_stock":
        short = r.get("shortfall")
        out = f"Found {r.get('total_on_hand')} on hand"
        out += f", {short} short." if short else (", enough to fill it." if short == 0 else ".")
        for i in r.get("incoming") or []:
            qty = f"{i['qty']}" if i.get("qty") is not None else "a reprint (quantity not recorded)"
            out += f" Incoming: {qty} from {i.get('vendor')}, expected {i.get('expected_arrival')}."
        return out
    if tool == "check_vendor_invoices":
        lines = []
        for v in r.get("vendors", [])[:3]:
            if v.get("will_ship_new_product"):
                lines.append(f"{v['name']} ships in {v['lead_days']} days and has no unpaid bills")
            else:
                n = len(v.get("open_invoices", []))
                late = max((i.get("days_overdue", 0) for i in v.get("open_invoices", [])), default=0)
                lines.append(f"{v['name']} will NOT ship: {n} unpaid invoice{'s' if n != 1 else ''} "
                             f"({_usd(v.get('open_balance'))}{f', {late} days overdue' if late else ''}); "
                             f"lead time {v['lead_days']} days once paid")
        return "; ".join(lines) + "."
    if tool == "get_lease_status":
        return (f"{r.get('landlord')} is owed {_usd(r.get('monthly_rent'))} for the {r.get('space_name')}, "
                f"due {r.get('next_due')} (in {r.get('days_until_due')} days).")
    if tool == "get_shop_date":
        return f"Today is {r.get('date_today')}."
    if tool == "get_ticket":
        t = r.get("ticket") or {}
        return f"Ticket #{t.get('id')}: {t.get('subject')} from {t.get('requester')}, currently {STATUS_WORDS.get(t.get('status'), t.get('status'))}."
    if tool == "list_tickets":
        return f"{r.get('count')} tickets on the board."
    if tool == "get_cash_balance":
        out = (f"{_usd(r.get('balance'))} in checking; {_usd(r.get('available_after_pending'))} free after "
               f"{r.get('pending_requests', 0)} pending approval(s).")
        up = r.get("upcoming_unqueued_bills") or []
        if up:
            bills = ", ".join(f"{_usd(u['amount'])} {KIND_WORDS.get(u['kind'], u['kind'])} to {u['payee']} due {u['due']}" for u in up)
            out += f" Bills coming up but not queued yet: {bills}; {_usd(r.get('available_after_upcoming'))} left after those."
        return out
    if tool == "check_price_margin":
        if "proposed_unit_price" in r:
            warn = " That is BELOW cost, so it can't be offered." if r.get("below_cost") else ""
            return (f"{_usd(r['proposed_unit_price'])} is {r.get('discount_pct_vs_list')}% off the "
                    f"{_usd(r.get('list_price'))} list price, leaving {_usd(r.get('margin_per_unit'))} margin per unit "
                    f"({r.get('margin_pct')}%).{warn}")
        return f"Costs {_usd(r.get('unit_cost'))}, lists at {_usd(r.get('list_price'))} ({r.get('list_margin_pct')}% margin)."
    if tool == "list_payments":
        return f"{r.get('count')} payment(s) made so far, totaling {_usd(r.get('total'))}."
    if tool == "list_payment_requests":
        return f"{r.get('count')} payment request(s) found."
    if tool == "update_ticket":
        t = r.get("ticket") or {}
        return f"Ticket is now {STATUS_WORDS.get(t.get('status'), t.get('status'))}."
    if tool == "save_draft":
        d = r.get("draft") or {}
        return f"Draft #{d.get('id')} to {d.get('recipient')} saved for your review. Nothing was sent."
    if tool == "draft_purchase_order":
        po = r.get("purchase_order") or {}
        ship = "can ship" if po.get("vendor_will_ship") else "can't ship until its unpaid invoice is paid"
        cash = "cash covers it" if po.get("cash_covers_total") else "cash does NOT cover it right now"
        return (f"PO #{po.get('id')}: {po.get('qty')} × {_usd(po.get('unit_cost'))} = {_usd(po.get('total'))}; "
                f"would arrive {po.get('expected_arrival_if_ordered_today')}; {po.get('recipient')} {ship}; {cash}.")
    if tool == "request_payment":
        q = r.get("request") or {}
        return (f"Request #{q.get('id')} queued: {_usd(q.get('amount'))} to {q.get('payee')}. "
                f"No money has moved; it waits for your approval.")
    if tool == "approve_payment":
        out = f"Paid {_usd(r.get('amount'))}. Checking is now {_usd(r.get('new_balance'))}."
        for i in r.get("incoming_stock") or []:
            qty = i["qty"] if i.get("qty") is not None else "a reprint of"
            out += f" {i.get('vendor')} can now ship {qty} {i.get('name') or i.get('sku')} size {i.get('size')}, expected {i.get('expected_arrival')}."
        if (r.get("related_update") or {}).get("vendor_will_ship_new_product"):
            out += " The vendor has no unpaid bills left, so it will take new orders."
        return out
    if tool == "reject_payment":
        return "Request rejected. No money moved."
    return ""


def narrate_tool(tool: str, args: Any, result: Any = None, with_result: bool = True) -> str:
    call = describe_call(tool, args if isinstance(args, dict) else {})
    # Swap a SKU code for its product name when the database result includes one.
    rows = result.get("rows") if isinstance(result, dict) else None
    if rows and isinstance(args, dict) and args.get("sku") and rows[0].get("name"):
        call = call.replace(str(args["sku"]), rows[0]["name"])
    res = describe_result(tool, result) if with_result else ""
    return f"{call}. {res}".strip() if res else f"{call}."
