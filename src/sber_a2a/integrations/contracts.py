from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sber_a2a.domain.models import DealRecord, DocumentRef, FulfillmentUpdate, Quote


@dataclass(frozen=True)
class OrderCreationResult:
    order_id: UUID
    payment_draft_id: UUID


class OrderGateway(Protocol):
    async def create_order_and_payment_draft(
        self,
        deal: DealRecord,
        quote: Quote,
        *,
        idempotency_key: str,
    ) -> OrderCreationResult: ...


class SupplierRiskGateway(Protocol):
    async def get_risk(self, supplier_id: str) -> Decimal: ...


class FulfillmentGateway(Protocol):
    async def create_demo_timeline(
        self,
        *,
        supplier_id: str,
    ) -> list[FulfillmentUpdate]: ...


class DocumentGateway(Protocol):
    async def create_demo_documents(
        self,
        *,
        deal: DealRecord,
        quote: Quote,
        order_id: UUID,
    ) -> list[DocumentRef]: ...
