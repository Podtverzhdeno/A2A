import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sber_a2a.domain.models import (
    ApprovalRequest,
    ApprovalResult,
    Comparison,
    CreateDealRequest,
    DealEvent,
    DealRecord,
    DealStatus,
    Quote,
    utc_now,
)
from sber_a2a.integrations.contracts import OrderGateway
from sber_a2a.services.store import DealNotFoundError, DealStore


class DealConflictError(RuntimeError):
    pass


class DealService:
    def __init__(
        self,
        graph,
        store: DealStore,
        order_gateway: OrderGateway,
    ) -> None:
        self._graph = graph
        self._store = store
        self._order_gateway = order_gateway
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

    @staticmethod
    def _record_from_state(draft: DealRecord, state: dict) -> DealRecord:
        return DealRecord(
            deal_id=draft.deal_id,
            status=DealStatus(state["status"]),
            intent=draft.intent,
            mandate=draft.mandate,
            supplier_ids=state["supplier_ids"],
            quotes=[Quote.model_validate(item) for item in state["quotes"]],
            comparison=(
                Comparison.model_validate(state["comparison"])
                if state["comparison"]
                else None
            ),
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
            if deal.status is DealStatus.ORDER_CREATED:
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

            created = await self._order_gateway.create_order_and_payment_draft(
                deal,
                evaluated.quote,
                idempotency_key=f"deal:{deal_id}:order",
            )
            order_id = created.order_id
            payment_draft_id = created.payment_draft_id
            updated = deal.model_copy(
                update={
                    "status": DealStatus.ORDER_CREATED,
                    "selected_quote_id": approval.quote_id,
                    "order_id": order_id,
                    "payment_draft_id": payment_draft_id,
                    "updated_at": utc_now(),
                    "events": [
                        *deal.events,
                        DealEvent(
                            event_type="quote_approved",
                            actor=f"human:{approval.approved_by}",
                            details={"quote_id": str(approval.quote_id)},
                        ),
                        DealEvent(
                            event_type="order_created",
                            actor="A3:sber",
                            details={
                                "order_id": str(order_id),
                                "payment_draft_id": str(payment_draft_id),
                            },
                        ),
                    ],
                }
            )
            await self._store.put(updated)
            return ApprovalResult(
                deal_id=deal_id,
                status=updated.status,
                selected_quote_id=approval.quote_id,
                order_id=order_id,
                payment_draft_id=payment_draft_id,
            )


__all__ = [
    "DealConflictError",
    "DealNotFoundError",
    "DealService",
]
