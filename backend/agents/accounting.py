from ..models import AgentName, AgentSpec

SPEC = AgentSpec(
    name=AgentName.ACCOUNTING,
    title="Accounting",
    description="Watches cash and invoices, checks margins on discounts, drafts purchase orders, and queues payments for human approval.",
    prompt_file="accounting.md",
    mcp_tools=[
        "get_shop_date", "get_ticket", "get_cash_balance", "check_vendor_invoices",
        "check_price_margin", "list_payments", "list_payment_requests",
        "draft_purchase_order", "request_payment", "update_ticket",
    ],
)
