import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sber_a2a.container import build_container
from sber_a2a.domain.models import (
    ApprovalRequest,
    CreateDealRequest,
    Mandate,
    ProcurementIntent,
    ProductRequest,
)


async def main() -> None:
    container = build_container()
    request = CreateDealRequest(
        intent=ProcurementIntent(
            customer_id="demo-customer",
            product=ProductRequest(
                sku="BEARING-6205-2RS",
                name="Подшипник 6205-2RS",
                quantity=20,
            ),
            delivery_city="Москва",
            delivery_by=date.today() + timedelta(days=10),
            max_total=Decimal("25000.00"),
        ),
        mandate=Mandate(
            customer_id="demo-customer",
            authorized_by="ivan.petrov",
            max_total=Decimal("25000.00"),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        ),
    )
    deal = await container.deals.create(request)
    print("=== A3 collected and ranked A2 quotes ===")
    print(deal.model_dump_json(indent=2))

    if deal.comparison and deal.comparison.recommended_quote_id:
        approval = await container.deals.approve(
            deal.deal_id,
            ApprovalRequest(
                quote_id=deal.comparison.recommended_quote_id,
                approved_by="ivan.petrov",
            ),
        )
        print("=== Human-approved order and payment draft ===")
        print(approval.model_dump_json(indent=2))


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
