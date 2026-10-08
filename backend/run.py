"""Command line entry point for the agent team (makes live gpt-6-luna calls).

  python -m backend.run --ticket 101            # one ticket, Boss starts
  python -m backend.run --board                 # all open tickets; resets the DB first
  python -m backend.run --board --no-reset      # board run without the reset
"""

import argparse
import asyncio

from .audit import read_events
from .models import Budget
from .spend import get_spend_limit, spend_since_reset
from .team import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--ticket", type=int, help="Ticket id to work.")
    target.add_argument("--board", action="store_true", help="Work every unresolved ticket.")
    parser.add_argument("--reset", action="store_true", help="Reset the working DB first (single ticket).")
    parser.add_argument("--no-reset", action="store_true", help="Skip the reset on a board run.")
    args = parser.parse_args()

    reset = args.reset or (args.board and not args.no_reset)
    budget = Budget(max_spend_usd=get_spend_limit())  # same $ safety rule as the dashboard
    summary = asyncio.run(run(None if args.board else args.ticket, reset=reset, budget=budget,
                              prior_spend_usd=spend_since_reset(read_events())))
    print(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
