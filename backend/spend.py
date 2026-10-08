"""Dollar spend: token prices, spend since the last reset, and the human-set spend limit.

The limit is a safety rule. team.py stops the agents once the spend since the last
reset reaches it, and main.py refuses to start a run when it has already been reached.
"""

import json
import os

from .config import DEFAULT_SPEND_LIMIT_USD, PRICE_INPUT_PER_M, PRICE_OUTPUT_PER_M, SETTINGS_PATH


def cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    return prompt_tokens * PRICE_INPUT_PER_M / 1_000_000 + completion_tokens * PRICE_OUTPUT_PER_M / 1_000_000


def step_tokens(event: dict) -> tuple[int, int]:
    usage = (event.get("detail") or {}).get("usage") or {}
    return int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))


def step_cost(event: dict) -> float:
    return cost_usd(*step_tokens(event))


def last_reset_index(events: list) -> int:
    return max((i for i, e in enumerate(events) if e.get("event") == "reset"), default=-1)


def spend_since_reset(events: list) -> float:
    start = last_reset_index(events)
    return sum(step_cost(e) for i, e in enumerate(events) if i > start and e.get("event") == "llm_step")


def get_spend_limit() -> float:
    try:
        return float(json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))["spend_limit_usd"])
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
        return DEFAULT_SPEND_LIMIT_USD


def set_spend_limit(limit_usd: float) -> float:
    if not limit_usd > 0:
        raise ValueError("The spend limit must be more than $0.")
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"spend_limit_usd": round(limit_usd, 4)}, indent=2), encoding="utf-8")
    os.replace(tmp, SETTINGS_PATH)
    return round(limit_usd, 4)


def prices() -> dict:
    return {"input_per_million_usd": PRICE_INPUT_PER_M, "output_per_million_usd": PRICE_OUTPUT_PER_M}
