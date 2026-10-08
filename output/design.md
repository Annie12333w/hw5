# Campus Customs Agent Desk: Design (draft for review)

The desk is the one screen a **human supervisor** uses to watch the agent team work, step in where money or customers are involved, and close tickets. It's built for three jobs, in this order:

1. **See what needs me.** Pending payments, drafts to review, tickets to close.
2. **Watch the team work** without reading raw JSON.
3. **Trust the result**: every number, tool call and decision can be traced.

Stack: React 19 + Vite + TypeScript in `frontend/`. It talks to the FastAPI backend at `http://localhost:8000`, and the backend allows only the Vite page origin `http://localhost:5173`.

---

## How to run

```bash
# Terminal 1: backend (from HW 5/backend)
python -m uvicorn main:app --reload --port 8000

# Terminal 2: the desk (from HW 5/frontend)
npm install        # first time only
npm run dev        # opens http://localhost:5173 in your browser
```
`uvicorn main:app --reload --port 8000` also works once `%APPDATA%\Python\Python314\Scripts` is on your PATH.

---

## Layout at a glance

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ CC Campus Customs │ Shop date │ Open │ Resolved │ Checking $ │ Agent spend │ 👤 🔔 ● Live │  ← metrics bar (navy, sticky)
├──────────────┬───────────────────────────────────────────────────────────────────────┤
│ TICKETS      │  #101 · Bulldog tee                          [Needs approval] [Run 2 ▾]│
│ ┌──────────┐ │ ┌───────────────────────────────────────────────────────────────────┐ │
│ │#101  ●   │ │ │                        🦁 Boss (navy suit)                         │ │  ← agent stage
│ │Bulldog   │ │ │                     ╱      │       │      ╲                        │ │    (hierarchy)
│ │[▶ Run]   │ │ │      🦫 Inventory  🦉 Accounting  🐻 Facilities  🐶 Cust. Service   │ │
│ └──────────┘ │ │      "8 on hand…"   "Queued #1…"   Not called    "Drafted…"       │ │
│ ┌──────────┐ │ │ Delegations: Boss → Inventory · Inventory → Accounting · …        │ │
│ │#102      │ │ └───────────────────────────────────────────────────────────────────┘ │
│ └──────────┘ │ ┌ Running log ─────────── [Everything|What they said|Tools|Flags] ──┐ │
│ ┌──────────┐ │ │ 🦁 Boss delegated: "Confirm stock for CC-TEE-WHITE…"   10:02:11   │ │  ← live log
│ │#103      │ │ │    🦫 Inventory used check_stock  [check_stock ▸]                  │ │    (indented by
│ └──────────┘ │ │       🦉 Accounting used request_payment [refused]              │ │     delegation depth)
│              │ └───────────────────────────────────────────────────────────────────┘ │
│ [↺ Reset]    │ ┌ What the team did ──────────────┬ Your move (1 waiting) ───────────┐ │  ← summary bar
│              │ │ Boss's final call …             │ Vendor invoice #501   $840.00    │ │    (after the run)
│              │ │ 🦫 Inventory · 2 tools · …      │ Checking $3,400 → $2,560          │ │
│              │ │ 🦉 Accounting · 3 tools · …     │ [✓ Approve $840] [✕ Reject…]      │ │
│              │ │ Not needed: Facilities          │ Drafts to review ▸ · [✓ Resolve]  │ │
└──────────────┴─┴─────────────────────────────────┴───────────────────────────────────┴─┘
```

The page reads top to bottom as **status, then choose, then watch, then decide**, which is the order a supervisor thinks in.

---

## 1. Metrics bar (top, sticky)

| Tile | Source | Why it's there |
|---|---|---|
| **Shop date** | `GET /metrics` → `desk.date_today` | The agents treat 2026-08-31 as "today", not the real date. Showing it stops a human from misreading "overdue". |
| **Open / Resolved** | `GET /metrics` | Progress at a glance. Resolved turns soft green when it isn't zero. |
| **Checking** | `cash_accounts` via `/metrics` | The one number that changes when you approve. The tile **flashes blue** when the balance drops, and its subtitle shows how much is waiting for approval. |
| **Agent spend** | `run_end` token usage in the audit trail | Shows the cost of the agents' work in **tokens and LLM calls** since the last reset. It isn't shown in dollars because the data has no price for gpt-6-luna, and we don't invent one. |
| **Spend bar ($)** | Every logged LLM step, priced at gpt-6-luna rates | Shows dollars spent since the last reset against **your $ limit** (click "of $3.00 limit ✎" to change it). The bar fills live and turns amber at 60% and red at 85%. At 100% the tile turns red, Run buttons lock, and the backend stops the agents. Every other spend bar (per agent, per run) uses the same $ limit as its scale, so they compare directly. |
| **Supervisor** | Your name (saved in the browser) | Recorded as `approved_by` on every payment. Approve and Resolve stay disabled until it's filled in. |
| **🔔 / 🔕** | Sound toggle | Turns the chime on or off. |
| **● Live / Offline** | Backend health | If the backend is down, a red banner gives the exact command to start it. |

**Why it's sticky and navy:** it's the frame of the app. It stays put while the log scrolls, and the dark band separates "facts about the shop" from "work in progress" below it.

## 2. Ticket column (left)

- One card per ticket: number, subject, type, requester, the item or lease it links to, and a status badge.
- **Click a card to open it.** The selected card shows a big **▶ Run agent team** button. Running is a deliberate second click because every run costs tokens and can queue real payments. A stray click only *views* a ticket.
- Cards flag **"💳 1 payment awaiting you"** (amber) and **"Agents working…"** (pulsing blue), so the ticket that needs you stands out without being opened.
- Only one run at a time, because the tickets share the same cash. Other Run buttons are disabled, with a tooltip saying which ticket is running.
- **↺ Reset shop data** sits at the bottom, away from the Run buttons, and asks for confirmation. It's destructive, so it's harder to hit by accident.

## 3. Workspace (right)

### 3a. Agent stage: the team, its hierarchy, who is working
- **The Boss sits on top, with dashed lines down to the four specialists.** This mirrors the actual flow: the Boss always starts and routes the work.
- **Highlighting while a ticket runs:**
  - **Working:** blue glow ring, the avatar gently bobs, and a "Working…" chip with a pulsing dot. The line from the Boss to that agent animates (marching dashes).
  - **Waiting:** light-blue card with "Waiting on Accounting". This makes nested delegation visible: the Boss waits on Inventory, which waits on Accounting.
  - **Done:** green ✓ badge on the avatar.
  - **Not called:** faded and greyed out. This shows the efficiency goal from the plan: on ticket 102, Inventory and Customer Service stay grey.
  - **Handoffs:** because of full connectivity, an agent may be called by another specialist. Its card then shows "↪ handed off by Inventory".
- **A mini $ spend bar on each agent card** shows that agent's dollar spend in the shown run against your $ limit, plus tokens and tool calls. It shimmers while that agent is working, so cost is visible per agent: you can see which specialist is expensive. A **"This run's spend"** bar under the stage totals the run.
- **A speech bubble under each agent** shows the latest thing it said (its reasoning, a delegation, or its final report), so you can follow the conversation without reading the log.
- **The delegation trail** under the stage lists every hand-off in order, for example *Boss → Inventory · Inventory → Accounting · Boss → Customer Service*. You can check it against the Expected plan in `output/desk_tickets.html`.

### 3b. Running log: what each agent is doing and thinking (in plain English)
- Agents narrate each step in a short plain sentence (required by their prompts). Tool calls are described by `backend/narrate.py`, for example *"Checking the shelf for Classic Bulldog Tee in size S (need 1). Found 0 on hand, 1 short."* The raw tool name and data stay behind a **details** link.
- Newest at the bottom. It **auto-scrolls while you're at the bottom**, and stops if you scroll up to read.
- Each entry has the agent's mini avatar, a plain-English headline ("Inventory used check_stock", "Boss delegated", "Guardrail stopped an action"), the agent's words (thinking in *italics*), and the time.
- **Entries are indented by delegation depth,** so the call tree reads like an outline.
- **Tool chips** (`check_stock ▸`) expand to show the exact arguments and the MCP result. That's the audit trail on demand, without a wall of JSON.
- **Colors:** refused tools and guardrail hits are amber, errors are red, and your own decisions are blue.
- **Filters:** *Everything · What they said · Tools · Guardrails & you*. A supervisor usually wants just the conversation, while an auditor wants just the tools.
- Three bouncing dots show the team is still working, the familiar "someone is typing" cue.

### 3c. Summary bar: the result and your move
It appears when the run finishes, and stays while anything is waiting for you.
- **Left, "What the team did":**
  - the Boss's final call
  - one line per specialist who worked: avatar, tool count, final report
  - a quiet "Not needed on this ticket: …" line for the agents who weren't called
- **Right, "Your move":** buttons with clear options.
  - **Payment / PO cards** show the payee, amount and the agent's reason. They also show the **cash impact before you click** ("Checking $3,400.00 → **$2,560.00**"), and turn red if the pay tool would refuse.
    - **✓ Approve $840.00:** the only button in the app that moves money. The amount is in the label so there's no ambiguity.
    - **✕ Reject…:** opens an inline reason box, because a rejection needs a why.
  - **Drafts to review:** customer, vendor and landlord messages and PO drafts, each badged **"Draft, not sent"**. Click to read the full text; agents never send anything.
  - **✓ Mark resolved:** with an optional closing note. It stays locked while a payment is pending, and the tooltip says why.
  - **↻ Run again:** re-runs the team on the same ticket. Earlier runs stay viewable from the **Run N ▾** picker.

---

## The cast: why animals, why these outfits

| Agent | Animal | Outfit | Why |
|---|---|---|---|
| Boss | 🦁 Lion | Navy suit, blue tie | The leader of the pride. The suit matches the navy header, so the Boss visually "owns" the page. |
| Inventory | 🦫 Beaver | Hard hat, hi-vis vest, clipboard | Beavers build and stockpile. The hard hat and clipboard say "warehouse". |
| Accounting | 🦉 Owl | Round glasses, banker's visor, calculator | The wise owl watching the numbers. The visor is the classic bookkeeper look. |
| Facilities | 🐻 Bear | Work cap, overalls, wrench | Sturdy and practical, the one who fixes the building. |
| Customer Service | 🐶 Golden retriever | Headset, polo shirt | Friendly and eager to help, and the headset says "support line". |

Why bother:
- **Faster recognition.** Five distinct silhouettes are quicker to scan in a busy log than five names.
- **Warmth.** Watching software spend money is stressful, and friendly mascots lower that tension without hiding any data.
- **No asset files.** The avatars are inline SVG, so they scale crisply and work offline.

The animals' fur colors are their own, but every *outfit* uses the app's blue/navy palette so the stage still looks like one system.

---

## Color system: blue, navy, white, gray (with contrast checks)

| Token | Hex | Used for | Contrast |
|---|---|---|---|
| navy-900 | `#0b1f3a` | Header, headings, Approve button | White on navy: **16.0:1** |
| blue-600 | `#1f4e8c` | Primary buttons, ticket numbers, links | White on blue: **8.3:1** |
| blue-500 | `#2f6fd0` | Active-agent glow, focus ring, live edges | Decorative, not used for text |
| blue-100 / blue-50 | `#e8eef8` / `#f4f7fc` | Selected card, waiting agent, page background | Body text on them: >14:1 |
| gray-900 | `#1d2433` | Body text | On white: **15.4:1** |
| gray-600 | `#4f5866` | Secondary text, timestamps | On white: **7.2:1** |
| gray-300 | `#cfd5de` | Borders only | n/a |

**Why blue and navy:** they read as calm, trustworthy and "finance". That suits a screen where you approve payments, and it doesn't compete with the colorful mascots.

**Small semantic accents, used sparingly** so they carry meaning:
- **Amber** = "needs you" (pending payment, refused tool, guardrail)
- **Green** = done or resolved
- **Red** = error, or a payment that would be refused

They're never the only signal: every state also has a text label or icon (✓, "Waiting on…", "refused"), so the desk works for color-blind users too.

Every text color meets WCAG AA (at least 4.5:1). Gray-400 is used only for disabled or idle visuals, never for text you need to read.

---

## Motion and sound

| Cue | When | Why |
|---|---|---|
| Glow + bobbing avatar | The agent currently making a move | Your eye goes straight to the action. |
| Marching dashed line | From the Boss to the specialist it's waiting on | Shows the hierarchy *in use*, not just drawn. |
| Entries slide in | A new log line | Signals "new" without flashing. |
| Checking tile flashes | Cash drops after an approval | Confirms the click had a real effect. |
| **Chime** (soft C-E-G bell) | The run finishes or fails | You can look away during a long run; the chime calls you back. It's made with the Web Audio API (no sound files), and the 🔔 button mutes it. Browsers only allow sound after a click, so the Run click turns it on. |
| Toasts (bottom right) | Run started or done, payment approved ("Paid $840.00 to Bulldog Print Co. Checking is now $2,560.00.") | Plain-English confirmation of every action. |

**`prefers-reduced-motion` turns off all animation.** Every state is still readable from its labels.

---

## Human-in-the-loop guardrails in the UI

- **Two-step run:** select a ticket, then press Run, so tokens and payments are never triggered by a stray click.
- **Approvals show the amount and the cash impact,** and need a supervisor name, which is stored as `approved_by`.
- **The backend has the final say:** the pay tool re-checks cash, and the UI shows the refusal if it says no.
- **Resolve is locked while a payment is pending.**
- **Reset needs confirmation**, and the audit trail is never cleared.
- **"Draft, not sent"** badges everywhere, because no message leaves the shop from this app.

---

## Which routes each part calls

| UI part | Routes | Refresh |
|---|---|---|
| Metrics bar | `GET /metrics` | Every 5 s (2 s while running) and after every action |
| Ticket column | `GET /tickets`, `GET /payments/pending` | Same |
| Run button | `POST /tickets/{id}/run`, then `GET /runs/{run_id}` | Run status every 1 s while running |
| Stage + log | `GET /events?ticket_id=&since=` | Every 1 s while running (only new events via `since`) |
| Summary: drafts | `GET /tickets/{id}` | When the ticket opens and after actions |
| Approve / Reject | `POST /payments/{id}/approve`, `/reject` | Then refreshes everything |
| Mark resolved | `POST /tickets/{id}/resolve` | Then refreshes everything |
| Reset | `POST /reset` | Then refreshes everything |

The three routes added for the desk were `/metrics`, `/tickets/{id}` and `/tickets/{id}/resolve`. A human resolve is recorded as `agent = "human"` in the ticket notes and the audit trail.

---

## Creative options

**Your six ideas** are all in this draft: the metrics bar, the ticket column, the workspace (cartoon stage, then log, then summary with action buttons), the blue/navy/white/gray palette with checked contrast, the working highlight plus hierarchy, and the completion chime.

**Extra ideas already in the draft:**
- **Supervisor name box**, so approvals are signed by a real person.
- **Cash-impact preview** on every payment card, plus a red "would be refused" warning.
- **"Not called" greyed agents**, plus a "Not needed on this ticket" line, so efficiency is visible at a glance.
- **Handoff chips** ("↪ handed off by Inventory") for specialist-to-specialist delegation.
- **Log filters**, plus **indentation by delegation depth**.
- **Expandable tool chips** with exact MCP arguments and results.
- **Run picker** to compare earlier runs of the same ticket.
- **Offline banner** with the exact command to start the backend.
- **Keyboard access** (cards and buttons are focusable, Enter selects), focus rings, and screen-reader-friendly live log updates.

**Ideas to consider next:**
1. **Expected vs actual overlay:** pull the Problem 6 plan in and tick off each expected delegation and tool as it happens, with a "matched plan" score.
2. **Replay scrubber:** drag a timeline slider to replay a finished run step by step, which is good for reviews and the reflection.
3. **Desktop notification** when the tab is hidden and a run finishes or a payment needs approval (alongside the chime).
4. **Spend meter per agent:** a small token bar on each card. It could show dollars if a gpt-6-luna price is added to config, never guessed.
5. **Agent moods:** expressions that change with state (focused while working, smiling when done, worried after a guardrail hit).
6. **"Board cleared" moment:** a small celebration when all three tickets are resolved.
7. **Night-shift (dark) theme** using the same navy palette, with contrast re-checked.
8. **Keyboard shortcuts:** `1`/`2`/`3` to pick a ticket, `R` to run, `A` to approve the focused payment (with confirmation).
9. **Read-aloud summary** using the browser's speech synthesis, for hands-free monitoring.
10. **Printable run report:** one click to save the summary, drafts and tool trail as a PDF for the audit file.

---

## Known limits of this draft
- It hasn't been run end to end against live gpt-6-luna yet. The type check and production build pass, and the backend routes were tested offline.
- Run status is kept in the backend's memory. If uvicorn reloads mid-run, the desk shows the events logged so far but loses the live status.
- The layout is designed for a laptop or desktop (≥ 1100 px). On narrow screens the columns stack and the hierarchy lines are hidden.
