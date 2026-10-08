from ..models import AgentName, AgentSpec

SPEC = AgentSpec(
    name=AgentName.CUSTOMER_SERVICE,
    title="Customer Service",
    description="Drafts clear, accurate messages to customers (never sends them).",
    prompt_file="customer_service.md",
    mcp_tools=["get_shop_date", "get_ticket", "update_ticket", "save_draft"],
)
