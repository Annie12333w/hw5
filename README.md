# Campus Customs: Multi-Agent Operations (HW 5)

A five-agent team (Boss, Inventory, Accounting, Facilities, Customer Service) works the shop's ticket board through an **MCP server** over a SQLite database. A **FastAPI backend** runs the agents, and a **React dashboard** lets a human supervisor watch them and approve payments. Agents use only **gpt-6-luna** via Portkey. Every payment needs human approval, and messages are drafts only.

## Layout

```
hw5/
├── AI_prompts.md            prompt log for every problem
├── requirements.txt         Python packages (MCP server + backend)
├── .env.example             copy to .env and add PORTKEY_API_KEY
├── .mcp.json                registers the MCP server for Claude Code
├── data/
│   ├── campus_customs.db        ORIGINAL database (read-only, used for resets)
│   └── campus_customs_new.db    WORKING copy (what the app reads and writes)
├── mcp_server/              server.py (16 MCP tools) + README.md
├── backend/                 main.py (FastAPI), models.py, team.py (agent loop), prompts/ (one per agent)
├── frontend/                React + Vite + TypeScript dashboard
└── output/                  harness.md, design.md, desk_tickets.html, resolved_*, audit_trail.json, ...
```

## Setup (once)

Tested with Python 3.14 and Node 24 (Vite 8 needs a recent Node, 20.19+).

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

Copy `.env.example` to `.env` (in this folder) and set `PORTKEY_API_KEY`. `.env` is git-ignored; never commit it.

## 1. Copy the original database to the working copy (clean run)

Do this whenever you want a clean run. The original is never modified.

```bash
python -m backend.reset_db
```

This copies `data/campus_customs.db` over `data/campus_customs_new.db` and archives old payment requests, drafts and incoming-stock records. The audit trail is kept. A manual copy also works: `cp data/campus_customs.db data/campus_customs_new.db` (Windows: `copy data\campus_customs.db data\campus_customs_new.db`).

## 2. Start the MCP server

```bash
python mcp_server/server.py
```

The server uses the stdio transport, so it waits for a client and prints nothing. You normally don't start it by hand:
- **The backend** launches its own copy automatically for every request and agent run.
- **Claude Code** starts it from `.mcp.json` (server name `campus-customs`) when you open this folder.

Running it by hand is a quick check that it starts without errors (Ctrl+C to stop).

## 3. Start the FastAPI backend (port 8000)

```bash
cd backend
uvicorn main:app --port 8000
```

- If `uvicorn` isn't on your PATH, use `python -m uvicorn main:app --port 8000`.
- `--reload` also works, but on Windows it can hang when it restarts, because of the MCP subprocess.
- API docs are at http://localhost:8000/docs.

## 4. Start the React board (port 5173)

```bash
cd frontend
npm run dev
```

This opens http://localhost:5173. The board calls the backend at http://localhost:8000, and the backend's CORS allows only this origin.

## 5. Reset before a full three-ticket run

Before running all three tickets, reset the working database (step 1, or **↺ Reset shop data** in the board's ticket column, which calls `POST /reset`). Then work the tickets **in order: 101 → 102 → 103**. Each approval changes cash, invoices and incoming stock for the next ticket.

1. Click a ticket, then **▶ Run agent team**. Watch the agents in the stage and the running log.
2. When a payment is requested, click **✓ Approve $…** in "Your move". It's signed "Supervisor #1" unless you type a name in the top bar. Approving is the only thing that moves cash.
3. Click **✓ Mark resolved** when nothing is pending.

From the original data you should see:
- **101:** approve $840 for invoice #501, then resolve. Checking goes $3,400 → $2,560.
- **102:** approve $2,400 rent, then resolve. Checking goes to $160.
- **103:** stays **blocked**. The $264 hoodie purchase order is $104 more than the cash left.

The top bar has a **$ spend limit** (default $3.00) on agent API spend; the backend stops the agents when it's reached.

## Outputs (`output/`)

| File | What it is |
|---|---|
| `harness.md` | Tables, MCP tools, agents, API routes, dashboard, safety rules, Problem 9 results |
| `design.md` | Dashboard design and rationale |
| `mcp_smoke.json` | Live test of the first three MCP tools |
| `desk_tickets.html` | Per ticket: Expected plan vs Actual; Cash and Reflection tabs (double-click to open) |
| `resolved_tickets.json` | Per ticket: status, outcome, what each agent did, human approvals |
| `resolved_board.html` | Dashboard screenshots after 101, 102 and 103 (double-click to open) |
| `audit_trail.json` | Append-only log of every agent step and human decision |
| `github_url.txt` | This repository's URL |

## Safety in one paragraph

Agents can only *request* payments. Approval is a human-only tool, the pay step refuses if cash is short, and cash only goes out. The original database is never written to. Drafts are never sent. Each agent has a narrow tool allowlist, and the backend fills in who acted, so agents can't impersonate each other. Runs have step, depth, token and dollar limits. Full details are in `output/harness.md`.
