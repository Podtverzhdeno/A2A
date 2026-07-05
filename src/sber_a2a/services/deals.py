from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sber_a2a.domain.models import (
    ApprovalRequest,
    ApprovalResult,
    ApprovalSnapshot,
    Comparison,
    CreateDealRequest,
    DealEvent,
    DealRecord,
    DealStatus,
    DocumentRef,
    FulfillmentUpdate,
    OrderState,
    OrderStatus,
    OutboxMessage,
    PaymentDraft,
    PaymentDraftStatus,
    Quote,
    utc_now,
)
from sber_a2a.integrations.contracts import (
    DocumentGateway,
    FulfillmentGateway,
    OrderGateway,
)
from sber_a2a.services.store import DealNotFoundError, DealStore


class DealConflictError(RuntimeError):
    pass


class DealService:
    def __init__(
        self,
        graph,
        store: DealStore,
        order_gateway: OrderGateway,
        fulfillment_gateway: FulfillmentGateway,
        document_gateway: DocumentGateway,
    ) -> None:
        self._graph = graph
        self._store = store
        self._order_gateway = order_gateway
        self._fulfillment_gateway = fulfillment_gateway
        self._document_gateway = document_gateway
        self._approval_lock = asyncio.Lock()
        self._background_tasks: set[asyncio.Task] = set()

    async def create(self, request: CreateDealRequest) -> DealRecord:
        deal = await self._create_draft(request)
        return await self._process(deal.deal_id)

    async def submit(self, request: CreateDealRequest) -> DealRecord:
        deal = await self._create_draft(request)
        self._schedule(deal.deal_id)
        return deal

    async def _create_draft(self, request: CreateDealRequest) -> DealRecord:
        deal_id = uuid4()
        deal = DealRecord(
            deal_id=deal_id,
            status=DealStatus.DRAFT,
            intent=request.intent,
            mandate=request.mandate,
            events=[
                DealEvent(
                    event_type="deal_created",
                    actor="A1:client",
                    details={"deal_id": str(deal_id)},
                )
            ],
        )
        await self._store.put(deal)
        return deal

    async def _process(self, deal_id: UUID) -> DealRecord:
        draft = await self._store.get(deal_id)
        initial_state = {
            "deal_id": str(deal_id),
            "intent": draft.intent.model_dump(mode="json"),
            "mandate": draft.mandate.model_dump(mode="json"),
            "supplier_ids": draft.supplier_ids,
            "quotes": [quote.model_dump(mode="json") for quote in draft.quotes],
            "comparison": (
                draft.comparison.model_dump(mode="json")
                if draft.comparison
                else None
            ),
            "status": draft.status.value,
            "errors": draft.errors,
            "events": [event.model_dump(mode="json") for event in draft.events],
        }
        try:
            result = initial_state
            async for snapshot in self._graph.astream(
                initial_state,
                {"configurable": {"thread_id": str(deal_id)}},
                stream_mode="values",
            ):
                result = snapshot
                deal = self._record_from_state(draft, result)
                await self._store.put(deal)
            deal = self._record_from_state(draft, result)
        except Exception as exc:
            deal = draft.model_copy(
                update={
                    "status": DealStatus.FAILED,
                    "errors": [*draft.errors, f"{type(exc).__name__}: {exc}"],
                    "events": [
                        *draft.events,
                        DealEvent(
                            event_type="workflow_failed",
                            actor="A3:sber",
                            details={"error_type": type(exc).__name__},
                        ),
                    ],
                    "updated_at": utc_now(),
                }
            )
        await self._store.put(deal)
        return deal

    @classmethod
    def _record_from_state(cls, draft: DealRecord, state: dict) -> DealRecord:
        comparison = (
            Comparison.model_validate(state["comparison"])
            if state["comparison"]
            else None
        )
        preview_snapshot = draft.approval_snapshot
        if (
            preview_snapshot is None
            and comparison is not None
            and comparison.recommended_quote_id is not None
        ):
            evaluated = next(
                (
                    item
                    for item in comparison.evaluated_quotes
                    if item.quote.quote_id == comparison.recommended_quote_id
                ),
                None,
            )
            if evaluated is not None and evaluated.eligible:
                preview_deal = draft.model_copy(update={"comparison": comparison})
                preview_snapshot = cls._build_approval_snapshot(
                    preview_deal,
                    evaluated,
                )
        return DealRecord(
            deal_id=draft.deal_id,
            status=DealStatus(state["status"]),
            intent=draft.intent,
            mandate=draft.mandate,
            supplier_ids=state["supplier_ids"],
            quotes=[Quote.model_validate(item) for item in state["quotes"]],
            comparison=comparison,
            approval_snapshot=preview_snapshot,
            errors=state["errors"],
            events=[DealEvent.model_validate(item) for item in state["events"]],
            created_at=draft.created_at,
            updated_at=utc_now(),
        )

    def _schedule(self, deal_id: UUID) -> None:
        task = asyncio.create_task(self._process(deal_id))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def resume_incomplete(self) -> None:
        for deal in await self._store.list(limit=200, status=DealStatus.DRAFT.value):
            self._schedule(deal.deal_id)

    async def get(self, deal_id: UUID) -> DealRecord:
        return await self._store.get(deal_id)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[DealRecord]:
        return await self._store.list(limit=limit, offset=offset, status=status)

    async def approve(
        self,
        deal_id: UUID,
        approval: ApprovalRequest,
    ) -> ApprovalResult:
        async with self._approval_lock:
            deal = await self._store.get(deal_id)
            if deal.status in {DealStatus.ORDER_CREATED, DealStatus.COMPLETED}:
                if (
                    deal.selected_quote_id == approval.quote_id
                    and deal.order_id is not None
                    and deal.payment_draft_id is not None
                ):
                    return ApprovalResult(
                        deal_id=deal_id,
                        status=deal.status,
                        selected_quote_id=approval.quote_id,
                        order_id=deal.order_id,
                        payment_draft_id=deal.payment_draft_id,
                        approval_snapshot_hash=(
                            deal.approval_snapshot.snapshot_hash
                            if deal.approval_snapshot
                            else ""
                        ),
                    )
                raise DealConflictError("Deal already has a different order")
            if deal.status is not DealStatus.AWAITING_APPROVAL:
                raise DealConflictError(
                    f"Deal cannot be approved from status {deal.status.value}"
                )
            if approval.approved_by != deal.mandate.authorized_by:
                raise DealConflictError("Approver is not authorized by the mandate")
            expires_at = deal.mandate.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                raise DealConflictError("Mandate has expired")
            if deal.comparison is None:
                raise DealConflictError("Deal has no comparison")

            evaluated = next(
                (
                    item
                    for item in deal.comparison.evaluated_quotes
                    if item.quote.quote_id == approval.quote_id
                ),
                None,
            )
            if evaluated is None or not evaluated.eligible:
                raise DealConflictError("Selected quote is missing or ineligible")
            if evaluated.quote.valid_until <= datetime.now(UTC):
                raise DealConflictError("Selected quote has expired")
            snapshot = self._build_approval_snapshot(deal, evaluated)
            if approval.approval_snapshot_hash != snapshot.snapshot_hash:
                raise DealConflictError("Approval snapshot hash does not match")

            created = await self._order_gateway.create_order_and_payment_draft(
                deal,
                evaluated.quote,
                idempotency_key=f"deal:{deal_id}:order",
            )
            order_id = created.order_id
            payment_draft_id = created.payment_draft_id
            now = utc_now()
            selected_supplier = evaluated.quote.supplier_id
            order = OrderState(
                order_id=order_id,
                supplier_id=selected_supplier,
                quote_id=approval.quote_id,
                status=OrderStatus.CONFIRMED_BY_SUPPLIER,
                confirmed_at=now,
            )
            payment_draft = PaymentDraft(
                payment_draft_id=payment_draft_id,
                order_id=order_id,
                amount=evaluated.quote.total_cost,
                currency=evaluated.quote.currency,
                payee_supplier_id=selected_supplier,
                status=PaymentDraftStatus.AWAITING_CUSTOMER_CONFIRMATION,
                created_at=now,
            )
            fulfillment = await self._fulfillment_gateway.create_demo_timeline(
                supplier_id=selected_supplier,
            )
            documents = await self._document_gateway.create_demo_documents(
                deal=deal,
                quote=evaluated.quote,
                order_id=order_id,
            )
            lifecycle_events = self._build_lifecycle_events(
                deal,
                approval,
                snapshot,
                order_id,
                payment_draft_id,
                selected_supplier,
                fulfillment,
                documents,
            )
            updated = deal.model_copy(
                update={
                    "status": DealStatus.COMPLETED,
                    "selected_quote_id": approval.quote_id,
                    "order_id": order_id,
                    "payment_draft_id": payment_draft_id,
                    "approval_snapshot": snapshot,
                    "order": order,
                    "payment_draft": payment_draft,
                    "fulfillment": fulfillment,
                    "documents": documents,
                    "updated_at": utc_now(),
                    "events": [*deal.events, *lifecycle_events],
                }
            )
            await self._store.put(updated)
            await self._append_and_publish_outbox(
                updated,
                evaluated.quote,
                snapshot,
                rejected_suppliers=[
                    supplier_id
                    for supplier_id in deal.supplier_ids
                    if supplier_id != selected_supplier
                ],
            )
            return ApprovalResult(
                deal_id=deal_id,
                status=updated.status,
                selected_quote_id=approval.quote_id,
                order_id=order_id,
                payment_draft_id=payment_draft_id,
                approval_snapshot_hash=snapshot.snapshot_hash,
            )

    @staticmethod
    def _build_approval_snapshot(deal: DealRecord, evaluated) -> ApprovalSnapshot:
        quote = evaluated.quote
        payload = {
            "deal_id": str(deal.deal_id),
            "quote_id": str(quote.quote_id),
            "supplier_id": quote.supplier_id,
            "sku": quote.sku,
            "quantity": quote.quantity,
            "total_cost": str(quote.total_cost),
            "currency": quote.currency,
            "delivery_days": quote.delivery_days,
            "warranty_months": quote.warranty_months,
            "payment_delay_days": quote.payment_delay_days,
            "ranking_version": deal.comparison.ranking_version if deal.comparison else "",
            "total_score": str(evaluated.total_score) if evaluated.total_score else None,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return ApprovalSnapshot(
            quote_id=quote.quote_id,
            supplier_id=quote.supplier_id,
            supplier_name=quote.supplier_name,
            sku=quote.sku,
            product_name=quote.product_name,
            quantity=quote.quantity,
            total_cost=quote.total_cost,
            currency=quote.currency,
            delivery_days=quote.delivery_days,
            warranty_months=quote.warranty_months,
            payment_delay_days=quote.payment_delay_days,
            ranking_version=payload["ranking_version"],
            total_score=evaluated.total_score,
            snapshot_hash=hashlib.sha256(encoded).hexdigest(),
        )

    @staticmethod
    def _build_lifecycle_events(
        deal: DealRecord,
        approval: ApprovalRequest,
        snapshot: ApprovalSnapshot,
        order_id: UUID,
        payment_draft_id: UUID,
        selected_supplier: str,
        fulfillment: list[FulfillmentUpdate],
        documents: list[DocumentRef],
    ) -> list[DealEvent]:
        rejected_suppliers = [
            supplier_id
            for supplier_id in deal.supplier_ids
            if supplier_id != selected_supplier
        ]
        events = [
            DealEvent(
                event_type="approval_snapshot_created",
                actor="A3:sber",
                details={
                    "snapshot_id": str(snapshot.snapshot_id),
                    "snapshot_hash": snapshot.snapshot_hash,
                },
            ),
            DealEvent(
                event_type="quote_approved",
                actor=f"human:{approval.approved_by}",
                details={
                    "quote_id": str(approval.quote_id),
                    "snapshot_hash": snapshot.snapshot_hash,
                },
            ),
            DealEvent(
                event_type="award_sent",
                actor="A3:sber",
                details={
                    "supplier_id": selected_supplier,
                    "quote_id": str(approval.quote_id),
                },
            ),
            *[
                DealEvent(
                    event_type="supplier_rejected",
                    actor="A3:sber",
                    details={"supplier_id": supplier_id},
                )
                for supplier_id in rejected_suppliers
            ],
            DealEvent(
                event_type="order_confirmed",
                actor=f"A2:{selected_supplier}",
                details={"order_id": str(order_id)},
            ),
            DealEvent(
                event_type="payment_draft_created",
                actor="A3:sber",
                details={
                    "payment_draft_id": str(payment_draft_id),
                    "status": PaymentDraftStatus.AWAITING_CUSTOMER_CONFIRMATION.value,
                },
            ),
        ]
        events.extend(
            DealEvent(
                event_type="fulfillment_updated",
                actor=update.actor,
                details={
                    "status": update.status.value,
                    **update.details,
                },
            )
            for update in fulfillment
        )
        events.extend(
            DealEvent(
                event_type="document_registered",
                actor="mock-edo",
                details={
                    "document_id": str(document.document_id),
                    "document_type": document.document_type,
                    "sha256": document.sha256,
                },
            )
            for document in documents
        )
        events.append(
            DealEvent(
                event_type="deal_completed",
                actor="A3:sber",
                details={"order_id": str(order_id)},
            )
        )
        return events

    async def _append_and_publish_outbox(
        self,
        deal: DealRecord,
        quote: Quote,
        snapshot: ApprovalSnapshot,
        *,
        rejected_suppliers: list[str],
    ) -> None:
        if deal.order_id is None or deal.payment_draft_id is None:
            return
        correlation_id = deal.events[-1].correlation_id if deal.events else uuid4()
        messages = [
            OutboxMessage(
                aggregate_id=deal.deal_id,
                recipient_agent_id=quote.supplier_id,
                message_type="sber.procurement.award.v1",
                idempotency_key=f"deal:{deal.deal_id}:award:{quote.supplier_id}",
                correlation_id=correlation_id,
                payload={
                    "deal_id": str(deal.deal_id),
                    "order_id": str(deal.order_id),
                    "quote_id": str(quote.quote_id),
                    "snapshot_hash": snapshot.snapshot_hash,
                },
            ),
            *[
                OutboxMessage(
                    aggregate_id=deal.deal_id,
                    recipient_agent_id=supplier_id,
                    message_type="sber.procurement.rejection.v1",
                    idempotency_key=(
                        f"deal:{deal.deal_id}:rejection:{supplier_id}"
                    ),
                    correlation_id=correlation_id,
                    payload={
                        "deal_id": str(deal.deal_id),
                        "selected_supplier_id": quote.supplier_id,
                    },
                )
                for supplier_id in rejected_suppliers
            ],
            OutboxMessage(
                aggregate_id=deal.deal_id,
                recipient_agent_id="payment-adapter",
                message_type="sber.procurement.payment_draft.v1",
                idempotency_key=f"deal:{deal.deal_id}:payment-draft",
                correlation_id=correlation_id,
                payload={
                    "deal_id": str(deal.deal_id),
                    "payment_draft_id": str(deal.payment_draft_id),
                    "amount": str(quote.total_cost),
                    "currency": quote.currency,
                },
            ),
            *[
                OutboxMessage(
                    aggregate_id=deal.deal_id,
                    recipient_agent_id=document.source,
                    message_type="sber.procurement.document_ref.v1",
                    idempotency_key=(
                        f"deal:{deal.deal_id}:document:{document.document_id}"
                    ),
                    correlation_id=correlation_id,
                    payload=document.model_dump(mode="json"),
                )
                for document in deal.documents
            ],
        ]
        append_outbox = getattr(self._store, "append_outbox", None)
        mark_published = getattr(self._store, "mark_outbox_published", None)
        if append_outbox is not None:
            await append_outbox(messages)
        if mark_published is not None:
            await mark_published(deal.deal_id)


__all__ = [
    "DealConflictError",
    "DealNotFoundError",
    "DealService",
]
