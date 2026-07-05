import asyncio
from decimal import Decimal
from uuid import uuid4

from sber_a2a.domain.models import DealRecord, Quote
from sber_a2a.integrations.contracts import OrderCreationResult


class MockOrderGateway:
    """Demo replacement for future ERP and Sber payment integrations."""

    def __init__(self) -> None:
        self._results: dict[str, OrderCreationResult] = {}
        self._lock = asyncio.Lock()

    async def create_order_and_payment_draft(
        self,
        deal: DealRecord,
        quote: Quote,
        *,
        idempotency_key: str,
    ) -> OrderCreationResult:
        async with self._lock:
            existing = self._results.get(idempotency_key)
            if existing is not None:
                return existing
            result = OrderCreationResult(
                order_id=uuid4(),
                payment_draft_id=uuid4(),
            )
            self._results[idempotency_key] = result
            return result


class MockSupplierRiskGateway:
    """A3-owned demo risk source; supplier payload cannot override these values."""

    def __init__(self) -> None:
        self._risks = {
            "supplier-a": Decimal("0.08"),
            "supplier-b": Decimal("0.15"),
            "supplier-c": Decimal("0.04"),
        }

    async def get_risk(self, supplier_id: str) -> Decimal:
        return self._risks.get(supplier_id, Decimal("0.50"))
