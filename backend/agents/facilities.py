from ..models import AgentName, AgentSpec

SPEC = AgentSpec(
    name=AgentName.FACILITIES,
    title="Facilities",
    description="Handles the shop space: leases, rent amounts and due dates, and landlord drafts.",
    prompt_file="facilities.md",
    mcp_tools=[
        "get_shop_date", "get_ticket", "get_lease_status", "get_cash_balance",
        "list_payments", "update_ticket", "save_draft",
    ],
)
