from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastmcp import FastMCP

from sber_a2a.container import Container
from sber_a2a.domain.models import (
    ApprovalRequest,
    CreateDealRequest,
    Mandate,
    ProcurementIntent,
    ProductRequest,
)


def create_mcp_server(container: Container) -> FastMCP:
    mcp = FastMCP(
        "Sber A3 Procurement Agent",
        instructions=(
            "A3 is the Sber orchestrator. It receives A1 procurement intents, "
            "requests quotes from multiple A2 supplier agents, compares them, "
            "and requires an authorized human before order creation."
        ),
    )

    @mcp.tool
    async def list_supplier_agents() -> list[dict]:
        """List accredited A2 supplier agents available to A3."""
        return [
            item.model_dump(mode="json")
            for item in container.registry.list_suppliers()
        ]

    @mcp.tool
    async def create_procurement_deal(
        customer_id: str,
        authorized_by: str,
        sku: str,
        product_name: str,
        quantity: int,
        delivery_city: str,
        delivery_by: str,
        max_total: float,
    ) -> dict:
        """Ask A3 to collect and compare supplier quotes for one product."""
        request = CreateDealRequest(
            intent=ProcurementIntent(
                customer_id=customer_id,
                product=ProductRequest(
                    sku=sku,
                    name=product_name,
                    quantity=quantity,
                ),
                delivery_city=delivery_city,
                delivery_by=date.fromisoformat(delivery_by),
                max_total=Decimal(str(max_total)),
            ),
            mandate=Mandate(
                customer_id=customer_id,
                authorized_by=authorized_by,
                max_total=Decimal(str(max_total)),
                expires_at=datetime.now(UTC) + timedelta(days=1),
            ),
        )
        deal = await container.deals.create(request)
        return deal.model_dump(mode="json")

    @mcp.tool
    async def get_procurement_deal(deal_id: str) -> dict:
        """Get the current A3 deal state and evidence events."""
        deal = await container.deals.get(UUID(deal_id))
        return deal.model_dump(mode="json")

    @mcp.tool
    async def approve_supplier_quote(
        deal_id: str,
        quote_id: str,
        approved_by: str,
    ) -> dict:
        """Authorize one eligible quote and create an order/payment draft."""
        result = await container.deals.approve(
            UUID(deal_id),
            ApprovalRequest(
                quote_id=UUID(quote_id),
                approved_by=approved_by,
            ),
        )
        return result.model_dump(mode="json")

    return mcp
