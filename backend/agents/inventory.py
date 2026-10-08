from ..models import AgentName, AgentSpec

SPEC = AgentSpec(
    name=AgentName.INVENTORY,
    title="Inventory",
    description="Checks stock by SKU and size, finds shortfalls, picks the vendor, and gives lead times / arrival dates.",
    prompt_file="inventory.md",
    mcp_tools=[
        "get_shop_date", "get_ticket", "check_stock", "check_vendor_invoices",
        "update_ticket", "save_draft",
    ],
)
