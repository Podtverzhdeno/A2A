from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sber_a2a.domain.models import (
    Comparison,
    ComponentScores,
    EvaluatedQuote,
    Mandate,
    ProcurementIntent,
    Quote,
)

HUNDRED = Decimal("100")
SCORE_STEP = Decimal("0.01")


def _score(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(HUNDRED, value)).quantize(
        SCORE_STEP,
        rounding=ROUND_HALF_UP,
    )


def _rejection_reasons(
    quote: Quote,
    intent: ProcurementIntent,
    mandate: Mandate,
    now: datetime,
) -> list[str]:
    reasons: list[str] = []
    if quote.sku != intent.product.sku:
        reasons.append("SKU does not match the request")
    if quote.quantity != intent.product.quantity:
        reasons.append("Quantity does not match the request")
    if quote.currency != intent.currency:
        reasons.append("Currency does not match the request")
    if quote.valid_until <= now:
        reasons.append("Quote has expired")

    remaining_days = (intent.delivery_by - date.today()).days
    if remaining_days < 0 or quote.delivery_days > remaining_days:
        reasons.append("Delivery date violates the hard deadline")

    max_total = min(
        mandate.max_total,
        intent.max_total if intent.max_total is not None else mandate.max_total,
    )
    if quote.total_cost > max_total:
        reasons.append("Total cost exceeds the mandate or intent limit")
    if (
        mandate.allowed_supplier_ids is not None
        and quote.supplier_id not in mandate.allowed_supplier_ids
    ):
        reasons.append("Supplier is not allowed by the mandate")
    return reasons


def compare_quotes(
    quotes: list[Quote],
    intent: ProcurementIntent,
    mandate: Mandate,
    *,
    now: datetime | None = None,
) -> Comparison:
    now = now or datetime.now(UTC)
    preliminary = [
        EvaluatedQuote(
            quote=quote,
            eligible=not (reasons := _rejection_reasons(quote, intent, mandate, now)),
            rejection_reasons=reasons,
        )
        for quote in quotes
    ]
    eligible = [item.quote for item in preliminary if item.eligible]

    if not eligible:
        return Comparison(
            evaluated_quotes=preliminary,
            recommended_quote_id=None,
            explanation="Нет оферт, удовлетворяющих обязательным ограничениям.",
        )

    minimum_cost = min(quote.total_cost for quote in eligible)
    minimum_delivery = min(quote.delivery_days for quote in eligible)
    weights = intent.weights

    evaluated: list[EvaluatedQuote] = []
    for item in preliminary:
        if not item.eligible:
            evaluated.append(item)
            continue

        quote = item.quote
        price = _score((minimum_cost / quote.total_cost) * HUNDRED)
        delivery = _score(
            HUNDRED
            if quote.delivery_days == 0
            else Decimal(minimum_delivery or 1) / Decimal(quote.delivery_days) * HUNDRED
        )
        warranty = _score(Decimal(quote.warranty_months) / Decimal("24") * HUNDRED)
        risk = _score((Decimal("1") - quote.supplier_risk) * HUNDRED)
        payment_terms = _score(
            Decimal(quote.payment_delay_days) / Decimal("30") * HUNDRED
        )
        scores = ComponentScores(
            price=price,
            delivery=delivery,
            warranty=warranty,
            risk=risk,
            payment_terms=payment_terms,
        )
        total = _score(
            price * weights.price
            + delivery * weights.delivery
            + warranty * weights.warranty
            + risk * weights.risk
            + payment_terms * weights.payment_terms
        )
        evaluated.append(
            EvaluatedQuote(
                quote=quote,
                eligible=True,
                scores=scores,
                total_score=total,
            )
        )

    evaluated.sort(
        key=lambda item: (
            item.eligible,
            item.total_score or Decimal("-1"),
            -item.quote.total_cost,
        ),
        reverse=True,
    )
    recommended = next(item for item in evaluated if item.eligible)
    explanation = (
        f"Рекомендуется {recommended.quote.supplier_name}: "
        f"итоговый балл {recommended.total_score}, "
        f"TCO {recommended.quote.total_cost} {recommended.quote.currency}, "
        f"поставка {recommended.quote.delivery_days} дн."
    )
    return Comparison(
        evaluated_quotes=evaluated,
        recommended_quote_id=recommended.quote.quote_id,
        explanation=explanation,
    )
