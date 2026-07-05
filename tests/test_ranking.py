from datetime import date, timedelta

from sber_a2a.domain.models import DealStatus


async def test_a3_collects_and_ranks_three_supplier_agents(
    container,
    deal_request,
) -> None:
    deal = await container.deals.create(deal_request)

    assert deal.status is DealStatus.AWAITING_APPROVAL
    assert len(deal.supplier_ids) == 3
    assert len(deal.quotes) == 3
    assert deal.comparison is not None
    assert deal.comparison.recommended_quote_id is not None

    recommended = next(
        item
        for item in deal.comparison.evaluated_quotes
        if item.quote.quote_id == deal.comparison.recommended_quote_id
    )
    assert recommended.quote.supplier_id == "supplier-c"
    assert recommended.eligible is True


async def test_hard_delivery_constraint_can_reject_all_quotes(
    container,
    deal_request,
) -> None:
    deal_request.intent.delivery_by = date.today() + timedelta(days=1)

    deal = await container.deals.create(deal_request)

    assert deal.status is DealStatus.FAILED
    assert deal.comparison is not None
    assert deal.comparison.recommended_quote_id is None
    assert all(
        "Delivery date violates the hard deadline" in item.rejection_reasons
        for item in deal.comparison.evaluated_quotes
    )


async def test_one_supplier_failure_allows_partial_success(
    container,
    deal_request,
    monkeypatch,
) -> None:
    supplier = container.registry.get("supplier-b")

    async def fail(_intent):
        raise TimeoutError("demo timeout")

    monkeypatch.setattr(supplier, "create_quote", fail)

    deal = await container.deals.create(deal_request)

    assert deal.status is DealStatus.AWAITING_APPROVAL
    assert len(deal.quotes) == 2
    assert any(
        event.event_type == "supplier_request_failed"
        for event in deal.events
    )
