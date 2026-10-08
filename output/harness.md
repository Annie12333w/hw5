# Campus Customs — Database Harness

**Original database:** `data/campus_customs.db`. Read-only. Used only as the source when we reset.
**Working copy:** `data/campus_customs_new.db`. The MCP server and backend read from and write to this copy.

Copy verified on 2026-10-06: both files have the same SHA-256 hash (`23686a90d698f7fa…`), and all 9 tables match row for row.

**Shop "today":** `desk.date_today` = **2026-08-31**. Every overdue or due-soon check uses this date, not the real clock.

**What this harness covers:**
- [Tables](#tables): all 9 database tables and how the tickets link to them
- [MCP tools](#mcp-tools-all-16-and-the-tables-they-use): all 16 tools and the tables they use
- [Agents](#agents): the five-agent team, its prompts, tool allowlists and agent loop
- [API routes](#backend-routes-problem-7): the FastAPI backend
- [Dashboard](#dashboard-problem-8): the React Agent Desk
- [Sequential tickets](#sequential-tickets-what-an-approval-changes): what each approval changes
- [Safety rules](#safety-and-guardrails): guardrails and spend limits
- [Problem 9 run](#problem-9-run-results): the real run, cash reconciliation and output files

**State outside the database** (all JSON, written only through the MCP server or backend):

| File | Holds | On reset |
|---|---|---|
| `data/payment_requests.json` | Payment requests waiting for, or decided by, the human | Archived, then emptied |
| `output/drafts.json` | Customer, vendor and landlord drafts and PO drafts (never sent) | Archived, then emptied |
| `data/incoming_stock.json` | Deliveries released by an approved invoice or PO (not yet on the shelf) | Archived, then emptied |
| `data/desk_settings.json` | The human's $ spend limit | Kept |
| `output/audit_trail.json` | Every agent step and human decision | **Kept, append-only** |

---

## Agent team

- **Boss:** reads tickets, routes the work, and makes the final call.
- **Inventory:** checks stock by SKU and size, spots shortfalls, and picks vendors.
- **Accounting:** watches cash and invoices, checks margins, and prepares payments or purchase orders.
- **Facilities:** handles leases and rent.
- **Customer Service:** drafts customer messages.

Any agent may delegate to any other agent.

---

## Tables

### 1. `desk` (1 row): the shop's clock
| Field | Type | Meaning |
|---|---|---|
| `date_today` | TEXT | The shop's current date (`2026-08-31`) |
| `notes` | TEXT | Free-form desk notes (currently NULL) |

**Why it matters:** this is the single source of truth for "today."
- Accounting uses it to decide whether an invoice is overdue (`due_date < date_today`).
- Facilities uses it to decide whether rent is due soon (`next_due - date_today`).
- Inventory uses it to compute vendor arrival dates (`date_today + lead_days`).
- Every agent should read it before any date reasoning.

### 2. `cash_accounts` (1 row): money available
| Field | Type | Meaning |
|---|---|---|
| `name` (PK) | TEXT | Account name (`checking`) |
| `balance` | REAL | Current balance ($3,400.00) |
| `date` | TEXT | Date the balance was last updated |

**Why it matters:**
- Accounting checks this before proposing any payment or purchase order.
- The **pay tool must refuse** any payment larger than `balance`.
- When a payment goes through, `balance` drops and `date` is set to `desk.date_today`.
- Cash only goes down in this model, because there is no revenue. Every dollar spent is gone for the rest of the run.

### 3. `inventory` (10 rows): stock on hand
| Field | Type | Meaning |
|---|---|---|
| `sku` (PK part) | TEXT | Product code, e.g. `CC-TEE-WHITE` |
| `name` | TEXT | Product display name |
| `size` (PK part) | TEXT | S / M / L / XL, or `OS` (one size) |
| `qty` | INTEGER | Units on hand |
| `location` | TEXT | Aisle in the shop |

**Why it matters:**
- Inventory looks up `(sku, size)` to see whether a request can be filled now and how large any shortfall is (`requested − qty`).
- Notable rows:
  - `CC-TEE-WHITE / S` = **0**
  - `CC-HOOD-NAVY / M` = **8**
  - `CC-MUG-CREST / OS` = **0**
- When an order is fulfilled, `qty` should go down.

### 4. `pricing` (4 rows): cost and price per SKU
| Field | Type | Meaning |
|---|---|---|
| `sku` (PK) | TEXT | Product code (links to `inventory.sku`) |
| `unit_cost` | REAL | What the shop pays per unit |
| `list_price` | REAL | Normal retail price |

| SKU | Cost | List | Margin |
|---|---|---|---|
| CC-HOOD-NAVY | $22.00 | $58.00 | 62% |
| CC-TEE-WHITE | $8.00 | $28.00 | 71% |
| CC-HAT-BLUE | $6.00 | $22.00 | 73% |
| CC-MUG-CREST | $3.50 | $14.00 | 75% |

**Why it matters:**
- Accounting uses it to check margins on discount requests. A discount must not push the price below `unit_cost`.
- It also prices purchase orders (`qty × unit_cost`).
- The Boss uses those margin checks to decide whether to approve a price override.

### 5. `vendors` (3 rows): suppliers and lead times
| Field | Type | Meaning |
|---|---|---|
| `id` (PK) | INTEGER | Vendor ID (referenced by `invoices.vendor_id`) |
| `name` | TEXT | Vendor name |
| `specialty` | TEXT | What they supply |
| `lead_days` | INTEGER | Days from order to delivery |

| id | Vendor | Specialty | Lead days |
|---|---|---|---|
| 1 | Bulldog Print Co | apparel reprint | 5 |
| 2 | Elm City Gifts | mugs and small goods | 3 |
| 3 | QuickShip CT | local courier | 1 |

**Why it matters:**
- Inventory picks a vendor for a restock based on `specialty`. There is no SKU-to-vendor table: apparel goes to vendor 1 and mugs go to vendor 2.
- **Lead times must come from `lead_days`**, never guessed.
- Before ordering, check whether the vendor has an open invoice (see `invoices`). **A vendor will not ship while an invoice is outstanding.**
- Agents may draft vendor messages but must not contact real vendors.

### 6. `invoices` (1 row): bills owed to vendors
| Field | Type | Meaning |
|---|---|---|
| `id` (PK) | INTEGER | Invoice number |
| `vendor_id` (FK → `vendors.id`) | INTEGER | Who is owed |
| `amount` | REAL | Amount owed |
| `due_date` | TEXT | When payment is due |
| `status` | TEXT | `open` or `paid` |
| `description` | TEXT | What the bill is for |

Current row: **#501, Bulldog Print Co, $840.00, due 2026-08-28, `open`**, "Rush reprint CC-TEE-WHITE S." It is **3 days overdue.**

**Why it matters:**
- Accounting watches these for overdue bills.
- An open invoice **blocks** that vendor from shipping, so Inventory can't restock apparel until #501 is paid.
- Paying requires **human approval**. Once paid, `status` must change to `paid` and a row must be added to `payments`.

### 7. `leases` (1 row): shop space
| Field | Type | Meaning |
|---|---|---|
| `id` (PK) | INTEGER | Lease ID (referenced by `tickets.lease_id`) |
| `space_name` | TEXT | The space being rented |
| `landlord` | TEXT | Who is paid |
| `monthly_rent` | REAL | Rent amount |
| `next_due` | TEXT | Next rent due date |
| `notes` | TEXT | Lease notes (NULL) |

Current row: **Chapel Street shop, Elm City Properties, $2,400.00, next due 2026-09-02** (2 days out).

**Why it matters:**
- Facilities owns this table and confirms the rent amount and due date.
- Accounting checks that cash covers it, and paying requires **human approval**.
- After payment, `next_due` should move forward one month (to 2026-10-02) and a row should be added to `payments`.

### 8. `payments` (0 rows): ledger of money out
| Field | Type | Meaning |
|---|---|---|
| `id` (PK) | INTEGER | Payment ID |
| `kind` | TEXT | What was paid, e.g. `invoice`, `rent`, `purchase_order` |
| `ref_id` | INTEGER | ID in the related table (`invoices.id`, `leases.id`, …) |
| `amount` | REAL | Amount paid |
| `account` | TEXT | Which `cash_accounts.name` it came from |
| `paid_at` | TEXT | Date paid (should use `desk.date_today`) |
| `approved_by` | TEXT | Name of the human approver. **Required.** |

**Why it matters:**
- This is the audit trail. Every approved payment writes exactly one row here.
- That write happens together with the cash deduction and the update to the related table (invoice status or lease `next_due`).
- `approved_by` records the human-approval rule in the data itself.
- The supervisor dashboard can show this ledger.

### 9. `tickets` (3 rows): the work board
| Field | Type | Meaning |
|---|---|---|
| `id` (PK) | INTEGER | Ticket number |
| `type` | TEXT | `customer_order`, `rent_notice`, `price_override`, … |
| `requester` | TEXT | Who opened it |
| `subject` | TEXT | Short title |
| `sku` | TEXT | Product involved (soft link to `inventory`/`pricing`) |
| `size` | TEXT | Size involved |
| `qty` | INTEGER | Quantity requested |
| `lease_id` (FK → `leases.id`) | INTEGER | Related lease, if any |
| `invoice_id` (FK → `invoices.id`) | INTEGER | Related invoice, if any |
| `status` | TEXT | `open`, then in progress, then resolved |
| `notes` | TEXT | Request details; agents can add findings here |
| `created_at` | TEXT | Timestamp opened |

**Why it matters:**
- This is what the Boss reads first. `type` plus the filled-in link columns tell the Boss which specialists to involve.
- The dashboard shows this board.
- Agents update `status` and `notes` as they resolve tickets.

---

## How the open tickets link to other tables

```
tickets.invoice_id ──FK──▶ invoices.id ──FK(vendor_id)──▶ vendors.id
tickets.lease_id   ──FK──▶ leases.id
tickets.sku/size   ··soft··▶ inventory(sku,size), pricing.sku
payments.ref_id    ··soft··▶ invoices.id | leases.id   (depends on payments.kind)
payments.account   ··soft··▶ cash_accounts.name
```
Only `invoice_id`, `lease_id` and `vendor_id` are declared foreign keys. The SKU and payment links are by convention, so the tools must check them in code.

### Ticket 101: customer order (Tauhid Zaman)
- **Request:** 1 × `CC-TEE-WHITE` in size **S**.
- **inventory:** `CC-TEE-WHITE / S` has **qty 0**, so it can't be filled from stock.
- **invoices:** `invoice_id = 501` points to the $840 bill for the rush reprint of this exact item. It is **overdue** (due 8/28, today 8/31).
- **vendors:** invoice 501 links to vendor 1, Bulldog Print Co, with **5 days** lead time. They won't ship until #501 is paid.
- **Path:**
  1. Accounting proposes paying #501.
  2. A human approves.
  3. The pay tool records the payment.
  4. Inventory confirms the reprint ETA (about 2026-09-05).
  5. Customer Service drafts an update to Tauhid.

### Ticket 102: rent notice (Elm City Properties)
- **leases:** `lease_id = 1` points to the Chapel Street shop, **$2,400 due 2026-09-02**.
- **cash_accounts:** checking has $3,400, so rent is affordable.
- **Path:**
  1. Facilities verifies the lease.
  2. Accounting prepares the payment.
  3. A human approves.
  4. The pay tool records the payment, deducts cash, and moves `next_due` to 2026-10-02.

### Ticket 103: price override (Yale AI Club)
- **Request:** 20 × `CC-HOOD-NAVY` in size **M**, at a bulk discount.
- **inventory:** only **8** in stock, so the shop is **12 short**.
- **pricing:** $22 cost against $58 list. Any discount must stay above $22 per unit.
- **vendors:** a hoodie reprint would go to Bulldog Print Co (apparel, 5 days). That is also **blocked by invoice 501** until it's paid.
- **Path:**
  1. Inventory reports the shortfall.
  2. Accounting proposes a discount that still protects the margin, and prices a 12-unit purchase order (12 × $22 = $264).
  3. The Boss decides.
  4. Customer Service drafts a reply to the club.

### How the tickets affect each other through cash
| Step | Cash |
|---|---|
| Start | $3,400 |
| Pay invoice 501 | −$840 → $2,560 |
| Pay rent | −$2,400 → **$160** |
| 12-hoodie purchase order | $264 > $160, so **the pay tool refuses** |

The tickets can't be solved in isolation. The Boss has to rank them by priority: the overdue bill and rent come first, and the bulk hoodie order is partial or deferred.

---

## MCP tools (Problem 3)

Server: `mcp_server/server.py` (FastMCP). Database: `data/campus_customs_new.db`. All three tools are read-only and return only stored values.

| Tool | Reads | Unlocks |
|---|---|---|
| `check_stock(sku, size?, requested_qty?)` | `inventory` | 101, 103 |
| `check_vendor_invoices(vendor_id?, invoice_id?)` | `vendors`, `invoices`, `desk` | 101, 103 |
| `get_lease_status(lease_id)` | `leases`, `desk` | 102 |

**`check_stock`**
- **Reads:** `inventory`
- **Unlocks:** tickets **101** and **103**
- **Why:** Ticket 101 asks for a `CC-TEE-WHITE` in size S and ticket 103 asks for 20 `CC-HOOD-NAVY` in size M. `check_stock` reads the exact quantity on hand for that SKU and size and returns the shortfall: 1 short for 101 because S is at 0, and 12 short for 103 because only 8 are in stock. That tells Inventory whether each order can ship from the shelf or needs a reprint.

**`check_vendor_invoices`**
- **Reads:** `vendors`, `invoices`, `desk`
- **Unlocks:** tickets **101** and **103**
- **Why:** Ticket 101 links to invoice 501, which is $840, open and 3 days overdue as of `desk.date_today`. `check_vendor_invoices` follows that invoice to Bulldog Print Co and shows the 5-day lead time and that the vendor won't ship while the invoice is open. That is the blocker for the tee reprint in 101, and for any hoodie reorder in 103 from the same apparel vendor.

**`get_lease_status`**
- **Reads:** `leases`, `desk`
- **Unlocks:** ticket **102**
- **Why:** Ticket 102 is Elm City Properties' rent notice, and it links to lease 1. `get_lease_status` reads that lease's $2,400 rent and its 2026-09-02 due date, and uses `desk.date_today` to show it is due in 2 days. Facilities and Accounting can then confirm the exact amount and deadline before asking a human to approve payment.

---

## Agent team and MCP tools (Problem 5)

Code lives in `backend/`:
- `models.py`: all data types
- `agents/`: one spec per agent, with its tool allowlist
- `prompts/`: one prompt file per agent
- `team.py`: the agent loop and delegation

Every agent runs on **`gpt-6-luna` through Portkey**, the only model allowed. Agents get shop data only by calling the `campus-customs` MCP server. The backend has no database code or shop tools of its own.

### Agents
| Agent | Prompt | Job | MCP tools it may call |
|---|---|---|---|
| **Boss** | `prompts/boss.md` | Reads the ticket, routes the work, ranks tickets by money and deadlines, makes the final call; the only agent that can resolve a ticket | `get_shop_date`, `list_tickets`, `get_ticket`, `get_cash_balance`, `list_payment_requests`, `update_ticket` |
| **Inventory** | `prompts/inventory.md` | Checks stock by SKU and size, finds shortfalls, picks the vendor by specialty, gives lead time and arrival date, spots vendors blocked by open invoices | `get_shop_date`, `get_ticket`, `check_stock`, `check_vendor_invoices`, `update_ticket`, `save_draft` (vendor) |
| **Accounting** | `prompts/accounting.md` | Watches cash and invoices, checks discount margins, drafts POs, queues payments for human approval | `get_shop_date`, `get_ticket`, `get_cash_balance`, `check_vendor_invoices`, `check_price_margin`, `list_payments`, `list_payment_requests`, `draft_purchase_order`, `request_payment`, `update_ticket` |
| **Facilities** | `prompts/facilities.md` | Confirms the lease, rent and due date; hands payment to Accounting; landlord drafts | `get_shop_date`, `get_ticket`, `get_lease_status`, `get_cash_balance`, `list_payments`, `update_ticket`, `save_draft` (landlord) |
| **Customer Service** | `prompts/customer_service.md` | Drafts honest, short customer messages; never sends | `get_shop_date`, `get_ticket`, `update_ticket`, `save_draft` (customer) |

**Full connectivity:** every agent also has `delegate(to_agent, task, context)`, which can target any other agent. It runs that agent's own loop and returns its report. Every agent ends with `finish(...)`, which returns an `AgentReport`.

**Agent loop** (`team.py`):
1. The model sees the agent's prompt, its task and its allowed tools.
2. The backend runs each tool call the model asks for: an MCP tool, `delegate`, or `finish`.
3. The results go back to the model, and the loop repeats within the budget.

The Boss always starts the run. Each step is appended to `output/audit_trail.json`, including:
- run_id, sequence number and UTC time
- shop date and ticket
- agent, delegation chain and depth
- the model's text and tool calls
- tool arguments, including values the backend injected
- the full tool result
- token use
- any guardrail hits and the final report

### MCP tools (all 16) and the tables they use
| Tool | Type | Tables / files | Used for |
|---|---|---|---|
| `check_stock` | read | `inventory`, `incoming_stock.json` | Stock and shortfall: 101 (tee S = 0), 103 (hoodie M = 8 of 20). Also lists **incoming** deliveries (not counted as on hand) |
| `check_vendor_invoices` | read | `vendors`, `invoices`, `desk` | Lead time, open invoices, `will_ship_new_product`: 101, 103 |
| `get_lease_status` | read | `leases`, `desk` | Rent amount and due date: 102 |
| `get_shop_date` | read | `desk` | Shop "today" for every date check |
| `list_tickets` | read | `tickets` | The board, so the Boss can rank tickets |
| `get_ticket` | read | `tickets` + linked `invoices`, `vendors`, `leases`, `inventory`, `pricing`; `drafts.json`, `payment_requests.json`, `incoming_stock.json` | One ticket and everything it links to |
| `get_cash_balance` | read | `cash_accounts`, `payment_requests.json`, `invoices`, `leases` | Balance, cash committed to pending requests, and **upcoming bills not yet queued** (open invoices, rent due within 7 days), giving `available_after_upcoming` |
| `check_price_margin` | read | `pricing` | Discount %, margin, `below_cost`: 103 |
| `list_payments` | read | `payments` | Prevents paying the same bill twice |
| `list_payment_requests` | read | `payment_requests.json` | What is waiting for the human |
| `update_ticket` | write | `tickets` (`status`, appended `notes`) | Progress notes; only the Boss or the human supervisor (via the dashboard) can resolve, and not while a payment is pending |
| `save_draft` | write | `output/drafts.json` (recipient read from `tickets`, `vendors` or `leases`) | Customer, vendor and landlord drafts; **never sent** |
| `draft_purchase_order` | write | `output/drafts.json` (reads `inventory`, `pricing`, `vendors`, `invoices`, `cash_accounts`) | PO priced at qty × `unit_cost`, with arrival date (today + `lead_days`), vendor-blocked flag and cash check: 103 |
| `request_payment` | write (no money) | `data/payment_requests.json` (checks `invoices`, `leases`, `cash_accounts`, `payments`) | Queues an invoice, rent or PO payment **for human approval**; refuses wrong amounts, duplicates, short cash and blocked vendors |
| `approve_payment` | **HUMAN ONLY**, moves money | `cash_accounts`, `payments`, `invoices` or `leases` (or PO draft), `tickets`, `incoming_stock.json` | One transaction: lower cash, add a `payments` row with `approved_by`, update the related row, and record the released goods as incoming; refuses if cash is short |
| `reject_payment` | **HUMAN ONLY** | `payment_requests.json` | Declines a request; no money moves |

Humans use the two human-only tools through the dashboard's Approve and Reject buttons (or `python -m backend.approve`). They are on no agent's allowlist, and the loop blocks them even if a model asks for them by name.

---

## Backend routes (Problem 7)

`backend/main.py` is a FastAPI app for the React dashboard. Start it from the `backend` folder with `python -m uvicorn main:app --port 8000` (`--reload` can hang on Windows because of the MCP subprocess); interactive docs are at `http://localhost:8000/docs`. Every route reads or changes shop data through the `campus-customs` MCP server. CORS allows only the Vite dashboard origin `http://localhost:5173`.

- `GET /health`: confirms the server is up, with the model, working database, MCP tool count and any active run.
- `GET /tickets`: returns the three tickets with their status and `is_open` (closed means `resolved`).
- `GET /tickets/{ticket_id}`: returns one ticket with its linked rows, drafts to review and payment requests (added for the desk in Problem 8).
- `POST /tickets/{ticket_id}/resolve` (body `{"resolved_by", "note"}`, both optional; the name defaults to "Supervisor #1"): the human's Mark resolved click. It is refused while a payment for the ticket is pending (Problem 8).
- `POST /tickets/{ticket_id}/run`: runs the agent team (Boss first) on one ticket. It returns a `run_id` right away (or waits if `{"wait": true}`), takes an optional `{"reset": true}`, and returns 409 if another run is still going.
- `GET /runs/{run_id}`: shows whether a run is running, done or failed, with the Boss's final report and token use.
- `GET /events?limit=&since=&ticket_id=&run_id=&include_before_reset=`: returns agent events from `audit_trail.json` in plain English: which agent acted, what it said, and which tools it used, with arguments, results and $ cost. By default only the **current session** (events after the last reset) is returned. Pass `since=next_cursor` to get only new events when refreshing the board.
- `GET /payments/pending`: lists the payment and purchase-order requests the agents prepared and are waiting for a human.
- `POST /payments/{request_id}/approve` (body optional; `approved_by` defaults to "Supervisor #1"): the human's Approve click. This is the only route that changes cash: it lowers `cash_accounts`, adds a `payments` row and updates the invoice, lease or PO. It refuses if cash is short.
- `POST /payments/{request_id}/reject` (body `{"rejected_by", "reason"}`): the human's Reject click. No money moves.
- `GET /cash`: returns the current `checking` balance from `cash_accounts`, plus the amount waiting for approval.
- `GET /metrics`: returns the desk's metrics bar: shop date, open and resolved counts, cash and pending amounts, and agent spend ($, tokens and LLM calls) since the last reset against the $ limit (Problem 8).
- `GET /settings`: returns the human's spend limit and the token prices used to price spend.
- `PUT /settings/spend-limit` (body `{"limit_usd": 3}`): sets the dollar limit on agent spend since the last reset. The agents stop when it is reached, and new runs are refused.
- `POST /reset`: restores `campus_customs_new.db` from the original `campus_customs.db` for a fresh run. It archives old drafts and requests, keeps the audit trail, and refuses while a run is in progress.

---

## Dashboard (Problem 8)

`frontend/` is a React 19 + Vite + TypeScript app. Start it with `npm run dev` in `frontend/`; it opens `http://localhost:5173`. It calls only the backend routes above at `http://localhost:8000`. The full design rationale is in `output/design.md`.

| Area | What it shows | Routes |
|---|---|---|
| **Metrics bar** (top, one row) | Shop date, open and resolved counts, checking balance (with amount awaiting approval), agent spend in $ with a loading bar against the human-set **$ limit** (click to change), and the approver name (default **Supervisor #1**) | `GET /metrics`, `PUT /settings/spend-limit` |
| **Ticket column** (left) | One card per ticket with status, "payment awaiting you" flags, **▶ Run agent team**, and **↺ Reset shop data** (starts a new session) | `GET /tickets`, `GET /payments/pending`, `POST /tickets/{id}/run`, `POST /reset` |
| **Ticket summary box** | The request, item and stock (plus incoming deliveries), pricing, linked invoice or lease, and what is waiting on the human | `GET /tickets/{id}` |
| **Agent stage** | Cartoon animals in work outfits (Boss lion, Inventory beaver, Accounting owl, Facilities bear, Customer Service retriever) in the Boss-on-top hierarchy. The working agent glows, waiting agents say who they are waiting on, unused agents are greyed "Not called", each card has a mini $ spend bar, and a delegation trail runs underneath | `GET /events`, `GET /runs/{id}` |
| **Running log** | Each agent step in plain English, indented by delegation depth, with expandable tool details and filters | `GET /events?since=` |
| **Summary and "Your move"** | The Boss's final call and each agent's report. Payment cards show **Approve $X** / **Reject** with a cash-impact preview; once approved they turn into a **light-green "You approved a payment of $X" box**. Also drafts to review, **Mark resolved**, and a "stopped early" banner if a limit cut a run short | `POST /payments/{id}/approve`, `POST /payments/{id}/reject`, `POST /tickets/{id}/resolve` |
| **Chime** | A soft bell when a run finishes (mute toggle in the top bar) | |

Opening the desk at `/?ticket=102` selects that ticket first; this was used for the Problem 9 screenshots.

---

## Sequential tickets: what an approval changes

Tickets are worked one after another, and each human approval updates the shop before the next ticket runs.

| Approval | Database / state changes | What later tickets see |
|---|---|---|
| Invoice #501 ($840, ticket 101) | `cash_accounts` −$840; `payments` row; `invoices.status = paid`; ticket 101 note; **incoming stock**: the Classic Bulldog Tee size S reprint from Bulldog Print Co, expected 2026-09-05 (quantity not recorded on the invoice) | `check_vendor_invoices`: Bulldog Print Co **will ship** new orders. `check_stock` for the tee shows the incoming reprint. |
| Rent request ($2,400, ticket 102) | `cash_accounts` −$2,400; `payments` row; `leases.next_due` → 2026-10-02 | `get_cash_balance` shows $160 |
| Purchase order (e.g. 12 hoodies, ticket 103) | `cash_accounts` −PO total; `payments` row; PO draft marked paid; **incoming stock** with qty and arrival = today + `lead_days` | `check_stock` shows the hoodies as incoming |

**Why incoming stock isn't added to the shelf count:** `desk.date_today` never advances, so goods can't arrive within the data. Adding them to `inventory.qty` would invent stock. Instead they are kept in `data/incoming_stock.json` (archived on reset) and returned by `check_stock` and `get_ticket` under `incoming`, separate from on-hand stock.

**Paying #501 does not bring hoodies.** Invoice #501 covers the white-tee reprint. Paying it unblocks Bulldog Print Co, so a hoodie purchase order becomes possible, but hoodies are only incoming once that PO is approved and paid. Tested live: after #501 and the rent are approved, ticket 103's agents report "Bulldog Print Co can ship" and draft a $264 PO, but don't request it, because only $160 is left.

**Upcoming bills:** `get_cash_balance` also lists open invoices and rent due within 7 days that nobody has queued yet (`available_after_upcoming`). This stops a ticket worked early from spending money a later ticket's rent needs.

**Reset = new session:** `POST /reset` restores the database and archives requests, drafts and incoming stock. The board then shows only events after the reset (`GET /events` filters by the last reset), so old runs, logs and resolved statuses disappear from the desk. The full history stays in `output/audit_trail.json`.

## Safety and guardrails

**Money**
- **Human approval for every payment.** Agents can only *request* a payment. `approve_payment` runs only from the human console, and it rejects an `approved_by` value that is empty or is an agent's name. Every payment row records who approved it.
- **Payment requests must match the database.** The amount must equal the invoice, rent or PO total exactly. The tool also refuses a request when:
  - the same item is already queued or paid
  - the PO's vendor still has an open invoice
  - the amount is more than `balance − pending requests`
- **The pay tool re-checks cash at approval time** and refuses if it's short. Cash only goes out.
- **One transaction per payment.** Cash, the ledger and the related row change together, or none of them change.
- **Discounts** can't go below `unit_cost`: `check_price_margin` flags `below_cost`. There is no discount policy in the data, so the final number is the Boss's call, and it reaches the customer only through a draft a human sends.

**Customers and outside parties**
- **Drafts only.** No tool can send email or contact a vendor or landlord. The recipient is always looked up in the database, so a model can't invent or redirect an address.
- **Customer Service never shares internal finances** (cash, unpaid bills, margins) and never promises dates or prices the data doesn't support.

**Data integrity and accountability**
- **Never invent data.** Tools return only stored values, plus `found: false` when a row is missing. Prompts require citing tool values.
- **No spoofing.** The backend fills in `agent` and `run_id` on every write. The model never sees those fields, and anything it sends for them is overwritten.
- **Least privilege.** Each agent has its own tool allowlist, so anything outside it has to go through delegation to the agent that owns it.
- **Ticket scope.** A single-ticket run can't change any other ticket.
- **Ticket notes are append-only,** with the date and agent stamped on each one.
- **The original database is read-only.** Both the server and backend refuse to run against it. `backend/reset_db.py` restores the working copy, and archives (never deletes) the drafts and payment requests.
- **The audit trail is append-only.** Every run adds to `audit_trail.json`, and nothing is ever removed. An unreadable file is renamed and kept.

**Dollar spend limit (set by the human)**
- The supervisor sets a $ limit in the dashboard's top bar (default $3.00). It is stored in `data/desk_settings.json`.
- Spend is priced at gpt-6-luna's published rates ($0.10 per 1M input tokens, $0.50 per 1M output tokens; set in `config.py` and overridable).
- `team.py` checks spend since the last reset before **every** model call and stops the team with `stopped_reason = "dollar spend limit reached"` once the limit is hit.
- `POST /tickets/{id}/run` refuses to start a run when the limit is already reached.
- Tested live: with $0.0015 of room left, the team stopped after 4 calls.

**Token and cost limits** (`Budget` in `models.py`, enforced in `team.py`)

| Limit | Default |
|---|---|
| LLM steps per agent loop (the last step forces `finish`) | 8 |
| Delegation depth | 3 |
| Agent loops per run | 14 |
| LLM calls per run | 45 |
| Tokens per run | 160k |
| Completion tokens per call | 1,500 |
| Tool output passed back to the model (characters) | 4,000 |
| Delegated task text (characters) | 1,500 |

- **No delegation cycles.** An agent can't delegate to anyone already waiting in its chain. It reports back instead.
- **Fresh context per delegation.** Each delegated agent starts with only its prompt and task, not the whole conversation.
- **Small tool lists.** Each agent sees only its own tools, so prompts stay short.
- **Stopping early.** When a limit is hit, the agent stops with `stopped_reason` and flags the ticket for a human. Model and tool errors end that agent, not the whole run.

---

## Problem 9 run results

A full run after a reset (2026-10-08 18:04 UTC), with tickets worked in order and the human approving between tickets:

| Ticket | Agents (delegations) | Human | Final status | Checking after |
|---|---|---|---|---|
| Start | n/a | n/a | n/a | **$3,400.00** |
| 101 Bulldog tee | Boss → Inventory, Boss → Accounting, Boss → Customer Service | Approved payment #1, $840.00 (invoice #501), resolved | resolved | $2,560.00 |
| 102 Rent due | Boss → Facilities → Accounting | Approved payment #2, $2,400.00 (rent, lease #1), resolved | resolved | $160.00 |
| 103 Bulk hoodies | Boss → Inventory, Boss → Accounting, Boss → Customer Service | None: left blocked ($264.00 PO vs $160.00, $104.00 short) | blocked | **$160.00** |

$3,400.00 − $840.00 − $2,400.00 = **$160.00** = `cash_accounts.balance` = the dashboard Checking tile. Agent API spend was $0.0227 (195,167 tokens, 51 LLM calls). That is model cost, not shop cash.

Outputs:
- `output/desk_tickets.html`: Actual sections and the Cash tab (Expected sections unchanged)
- `output/resolved_tickets.json`: per ticket: ID, final status, outcome, what each agent did, human approvals
- `output/resolved_board.html`: double-clickable, with dashboard screenshots after 101, 102 and 103 (`output/screenshots/`)
- `output/audit_trail.json`: the real runs, written live and append-only

---

## Rules the tools and agents must enforce
1. "Today" is `desk.date_today`, never the system clock.
2. Lead times come only from `vendors.lead_days`.
3. A vendor with an `open` invoice will not ship new product.
4. **Every payment needs human approval** (`approved_by` cannot be empty).
5. A payment must update `cash_accounts`, insert a row into `payments`, and update the related row (`invoices.status` or `leases.next_due`), all in one transaction.
6. If `amount > balance`, the pay tool **refuses**.
7. Cash only goes out, because no revenue is modeled.
8. Before a full ticket run, **reset** `campus_customs_new.db` from `campus_customs.db`.
9. No real emails or vendor contact. **Drafts only.**
10. The original `campus_customs.db` is never written to.
