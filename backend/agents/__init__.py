"""Agent registry. Each agent has one spec file here and one prompt file in backend/prompts/."""

from ..config import PROMPTS_DIR
from ..models import AgentName, AgentSpec
from . import accounting, boss, customer_service, facilities, inventory

AGENTS: dict[AgentName, AgentSpec] = {
    m.SPEC.name: m.SPEC for m in (boss, inventory, accounting, facilities, customer_service)
}

# Tools only a human supervisor may call. No agent allowlist may contain them,
# and the agent loop blocks them even if a model asks for them by name.
HUMAN_ONLY_TOOLS = frozenset({"approve_payment", "reject_payment"})

for _spec in AGENTS.values():
    assert not HUMAN_ONLY_TOOLS & set(_spec.mcp_tools), f"{_spec.name} must not hold a human-only tool"


def load_prompt(spec: AgentSpec) -> str:
    return (PROMPTS_DIR / spec.prompt_file).read_text(encoding="utf-8")
