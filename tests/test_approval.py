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
        ApprovalRequest(
            quote_id=quote_id,
            approved_by="approver-1",
            approval_snapshot_hash=deal.approval_snapshot.snapshot_hash,
        ),
    )

    assert result.status is DealStatus.COMPLETED
    assert result.approval_snapshot_hash
    stored = await container.deals.get(deal.deal_id)
    assert stored.order_id == result.order_id
    assert stored.payment_draft_id == result.payment_draft_id
    assert stored.approval_snapshot is not None
    assert stored.approval_snapshot.snapshot_hash == result.approval_snapshot_hash
    assert stored.order is not None
    assert stored.payment_draft is not None
    assert stored.fulfillment[-1].status.value == "completed"
    assert {document.document_type for document in stored.documents} == {
        "invoice",
        "waybill",
        "acceptance_certificate",
    }

    repeated = await container.deals.approve(
        deal.deal_id,
        ApprovalRequest(
            quote_id=quote_id,
            approved_by="approver-1",
            approval_snapshot_hash=deal.approval_snapshot.snapshot_hash,
        ),
    )
    assert repeated.order_id == result.order_id
    assert repeated.payment_draft_id == result.payment_draft_id
    assert repeated.approval_snapshot_hash == result.approval_snapshot_hash


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
                approval_snapshot_hash=deal.approval_snapshot.snapshot_hash,
            ),
        )


async def test_approval_requires_current_snapshot_hash(
    container,
    deal_request,
) -> None:
    deal = await container.deals.create(deal_request)

    with pytest.raises(DealConflictError, match="snapshot hash"):
        await container.deals.approve(
            deal.deal_id,
            ApprovalRequest(
                quote_id=deal.comparison.recommended_quote_id,
                approved_by="approver-1",
                approval_snapshot_hash="0" * 64,
            ),
        )
