# Campus Customs MCP Server

## What it's for
This server is the shared toolbox for the Campus Customs multi-agent team: Boss, Inventory, Accounting, Facilities and Customer Service. Agents never query the database directly. The backend (`../backend/`) connects to this server over stdio and gives each agent only the tools on its allowlist.

Each tool:
- returns only what is stored in the database, and never invents values
- treats `desk.date_today` as "today"
- reports `found: false` or `ok: false` with a reason, instead of guessing

## What files it uses
- **Working database:** `../data/campus_customs_new.db`. You can override this with `CAMPUS_DB_PATH`.
- **Original database:** `../data/campus_customs.db`. The server never opens it and refuses to start if pointed at it. It is used only by `backend/reset_db.py` to reset the working copy.
- **Drafts:** `../output/drafts.json`. Messages and purchase orders saved for human review; nothing is ever sent. Override with `CAMPUS_DRAFTS_PATH`.
- **Payment requests:** `../data/payment_requests.json`. Requests waiting for human approval. Override with `CAMPUS_REQUESTS_PATH`.

## Tools (16)

### Read
| Tool | Reads | Purpose |
|---|---|---|
| `check_stock(sku, size?, requested_qty?)` | `inventory` | Quantity on hand and location; shortfall when `requested_qty` is given |
| `check_vendor_invoices(vendor_id?, invoice_id?)` | `vendors`, `invoices`, `desk` | Lead time, open invoices with days overdue, `will_ship_new_product`; with no arguments, every vendor |
| `get_lease_status(lease_id)` | `leases`, `desk` | Landlord, rent, next due date, days until due |
| `get_shop_date()` | `desk` | The shop's "today" |
| `list_tickets(status?)` | `tickets` | The ticket board |
| `get_ticket(ticket_id)` | `tickets` + linked `invoices`, `vendors`, `leases`, `inventory`, `pricing`; drafts and requests | One ticket and everything it links to |
| `get_cash_balance(account?)` | `cash_accounts`, payment requests | Balance, pending total, `available_after_pending` |
| `check_price_margin(sku, proposed_unit_price?, qty?)` | `pricing` | Margin, discount %, `below_cost`, order totals |
| `list_payments(kind?, ref_id?)` | `payments` | The ledger of payments already made |
| `list_payment_requests(status?)` | payment requests | Requests waiting for or decided by the human |

### Agent write tools (no money moves)
| Tool | Writes | Purpose |
|---|---|---|
| `update_ticket(ticket_id, agent, status?, note?)` | `tickets` | Sets status and appends a dated note. Only the Boss or the human supervisor (`agent="human"`, set only by the dashboard route) can resolve, and not while a payment is pending |
| `save_draft(ticket_id, kind, subject, body, agent, vendor_id?, lease_id?)` | `drafts.json` | Customer, vendor or landlord draft; the recipient comes from the database |
| `draft_purchase_order(ticket_id, sku, size, qty, vendor_id, agent)` | `drafts.json` | PO at qty × `unit_cost`, with arrival date, vendor-blocked flag and cash check |
| `request_payment(kind, ref_id, amount, ticket_id, reason, agent)` | `payment_requests.json` | Queues an invoice, rent or PO payment for human approval. Refuses wrong amounts, duplicates, short cash and vendors with open invoices |

### Human-only (never given to agents)
| Tool | Writes | Purpose |
|---|---|---|
| `approve_payment(request_id, approved_by)` | `cash_accounts`, `payments`, `invoices` or `leases` (or PO draft), `tickets` | In one transaction: lowers cash, adds a `payments` row, and updates the related row (invoice → `paid`, lease `next_due` + 1 month). Refuses if cash is short |
| `reject_payment(request_id, rejected_by, reason)` | `payment_requests.json` | Declines a request; no money moves |

The backend fills in the `agent` and `run_id` parameters itself, so a model can't claim to be another agent.

## Running
```bash
pip install -r ../requirements.txt   # from mcp_server/; or `pip install -r requirements.txt` from the repo root
python server.py
```
The server uses the stdio transport. Claude Code connects through `../.mcp.json`, and the backend starts the server itself. The import tries `fastmcp.FastMCP` first. If that isn't installed, it falls back to `mcp`'s `MCPServer`, which is the same FastMCP API under its mcp 2.x name.
