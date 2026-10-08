from ..models import AgentName, AgentSpec

SPEC = AgentSpec(
    name=AgentName.BOSS,
    title="Boss",
    description="Reads tickets, decides who works on them and in what order, and makes the final call.",
    prompt_file="boss.md",
    mcp_tools=[
        "get_shop_date", "list_tickets", "get_ticket", "get_cash_balance",
        "list_payment_requests", "update_ticket",
    ],
)
