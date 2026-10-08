"""Human supervisor console for payment requests. Agents can never run this.

  python -m backend.approve list
  python -m backend.approve approve 1 --by "Annie Wang"
  python -m backend.approve reject 1 --by "Annie Wang" --reason "Pay next week"

Calls the human-only MCP tools (approve_payment / reject_payment) and appends
the decision to output/audit_trail.json.
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from .audit import AuditLog
from .mcp_client import ShopMCP
from .models import AuditEventType


async def decide(mcp: ShopMCP, tool: str, call_args: dict) -> tuple[bool, Any]:
    """Run a human-only MCP tool (approve_payment / reject_payment) and audit the decision.

    Shared by this CLI and the dashboard's approve/reject routes in main.py.
    """
    assert tool in ("approve_payment", "reject_payment")
    ok, result = await mcp.call(tool, call_args)
    _, desk = await mcp.call("get_shop_date", {})
    audit = AuditLog(f"human-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    audit.shop_date = desk.get("date_today") if isinstance(desk, dict) else None
    if isinstance(result, dict):
        audit.ticket_id = (result.get("request") or {}).get("ticket_id")
    audit.log(AuditEventType.HUMAN_DECISION, agent="human", tool=tool, arguments=call_args, ok=ok, result=result)
    return ok, result


async def _main(args: argparse.Namespace) -> None:
    async with ShopMCP() as mcp:
        if args.cmd == "list":
            _, result = await mcp.call("list_payment_requests", {"status": "pending_approval"})
        elif args.cmd == "approve":
            _, result = await decide(mcp, "approve_payment",
                                     {"request_id": args.request_id, "approved_by": args.by})
        else:
            _, result = await decide(mcp, "reject_payment",
                                     {"request_id": args.request_id, "rejected_by": args.by, "reason": args.reason})
        print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve or reject agent payment requests.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    a = sub.add_parser("approve")
    a.add_argument("request_id", type=int)
    a.add_argument("--by", required=True, help="Name of the human approver.")
    r = sub.add_parser("reject")
    r.add_argument("request_id", type=int)
    r.add_argument("--by", required=True)
    r.add_argument("--reason", required=True)
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
