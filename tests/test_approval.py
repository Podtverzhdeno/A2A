import pytest

from sber_a2a.domain.models import ApprovalRequest, DealStatus
from sber_a2a.services.deals import DealConflictError


async def test_authorized_human_creates_one_order_and_payment_draft(
    container,
    deal_request,
) -> None:
    deal = await container.deals.create(deal_request)
    quote_id = deal.comparison.recommended_quote_id

    result = await container.deals.approve(
        deal.deal_id,
        ApprovalRequest(quote_id=quote_id, approved_by="approver-1"),
    )

    assert result.status is DealStatus.ORDER_CREATED
    stored = await container.deals.get(deal.deal_id)
    assert stored.order_id == result.order_id
    assert stored.payment_draft_id == result.payment_draft_id

    repeated = await container.deals.approve(
        deal.deal_id,
        ApprovalRequest(quote_id=quote_id, approved_by="approver-1"),
    )
    assert repeated.order_id == result.order_id
    assert repeated.payment_draft_id == result.payment_draft_id


async def test_unauthorized_human_cannot_approve(
    container,
    deal_request,
) -> None:
    deal = await container.deals.create(deal_request)

    with pytest.raises(DealConflictError, match="not authorized"):
        await container.deals.approve(
            deal.deal_id,
            ApprovalRequest(
                quote_id=deal.comparison.recommended_quote_id,
                approved_by="unknown-user",
            ),
        )
