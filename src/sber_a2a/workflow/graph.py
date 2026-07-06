import asyncio
from datetime import UTC, datetime
from typing import Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from sber_a2a.domain.models import (
    Comparison,
    DealEvent,
    DealStatus,
    Mandate,
    ProcurementIntent,
    Quote,
)
from sber_a2a.domain.ranking import compare_quotes
from sber_a2a.integrations.contracts import SupplierRiskGateway
from sber_a2a.services.llm import LanguageModelService
from sber_a2a.suppliers.mock import SupplierRegistry


class WorkflowState(TypedDict):
    deal_id: str
    intent: dict
    mandate: dict
    supplier_ids: list[str]
    quotes: list[dict]
    comparison: dict | None
    status: str
    errors: list[str]
    events: list[dict]


def _event(
    event_type: str,
    details: dict | None = None,
    *,
    actor: str = "A3:sber",
) -> dict:
    return DealEvent(
        event_type=event_type,
        actor=actor,
        details=details or {},
    ).model_dump(mode="json")


def build_procurement_graph(
    registry: SupplierRegistry,
    llm: LanguageModelService,
    risk_gateway: SupplierRiskGateway,
    *,
    minimum_quotes: int = 2,
):
    async def validate_mandate(state: WorkflowState) -> dict:
        intent = ProcurementIntent.model_validate(state["intent"])
        mandate = Mandate.model_validate(state["mandate"])
        errors = list(state["errors"])
        expires_at = mandate.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            errors.append("Mandate has expired")
        if intent.product.category not in mandate.allowed_categories:
            errors.append("Product category is not allowed by the mandate")
        if intent.max_total is not None and intent.max_total > mandate.max_total:
            errors.append("Intent limit exceeds mandate limit")
        return {
            "errors": errors,
            "events": state["events"]
            + [
                _event(
                    "mandate_validated",
                    {
                        "target": "policy-engine",
                        "message_type": "sber.procurement.mandate_check.v1",
                        "valid": not errors,
                        "payload_summary": {
                            "mandate_id": str(mandate.mandate_id),
                            "authorized_by": mandate.authorized_by,
                            "category": intent.product.category,
                            "max_total": str(mandate.max_total),
                        },
                    },
                )
            ],
        }

    def route_after_validation(state: WorkflowState) -> Literal["discover", "finalize"]:
        return "finalize" if state["errors"] else "discover"

    async def discover_suppliers(state: WorkflowState) -> dict:
        intent = ProcurementIntent.model_validate(state["intent"])
        mandate = Mandate.model_validate(state["mandate"])
        agents = registry.discover(
            intent.product.category,
            mandate.allowed_supplier_ids,
        )
        supplier_ids = [agent.summary.supplier_id for agent in agents]
        errors = list(state["errors"])
        if len(supplier_ids) < minimum_quotes:
            errors.append(
                f"At least {minimum_quotes} eligible supplier agents are required"
            )
        return {
            "supplier_ids": supplier_ids,
            "errors": errors,
            "events": state["events"]
            + [
                _event(
                    "suppliers_discovered",
                    {
                        "target": "agent-registry",
                        "message_type": "sber.procurement.supplier_discovery.v1",
                        "count": len(supplier_ids),
                        "supplier_ids": supplier_ids,
                    },
                )
            ],
        }

    def route_after_discovery(state: WorkflowState) -> Literal["request_quotes", "finalize"]:
        return "finalize" if state["errors"] else "request_quotes"

    async def request_quotes(state: WorkflowState) -> dict:
        intent = ProcurementIntent.model_validate(state["intent"])
        agents = [
            agent
            for supplier_id in state["supplier_ids"]
            if (agent := registry.get(supplier_id)) is not None
        ]
        events = [
            *state["events"],
            *[
                _event(
                    "rfq_sent",
                    {
                        "target": f"A2:{agent.summary.supplier_id}",
                        "message_type": "sber.procurement.rfq.v1",
                        "supplier_id": agent.summary.supplier_id,
                        "payload_summary": {
                            "sku": intent.product.sku,
                            "quantity": intent.product.quantity,
                            "category": intent.product.category,
                            "delivery_city": intent.delivery_city,
                            "delivery_by": str(intent.delivery_by),
                        },
                    },
                )
                for agent in agents
            ],
        ]
        results = await asyncio.gather(
            *(agent.create_quote(intent) for agent in agents),
            return_exceptions=True,
        )
        quotes: list[Quote] = []
        errors = list(state["errors"])
        for agent, result in zip(agents, results, strict=True):
            if isinstance(result, Exception):
                events.append(
                    _event(
                        "supplier_request_failed",
                        {
                            "target": "A3:sber",
                            "message_type": "sber.procurement.quote.v1",
                            "supplier_id": agent.summary.supplier_id,
                            "error_type": type(result).__name__,
                        },
                    )
                )
            elif result is not None:
                quotes.append(result)
                events.append(
                    _event(
                        "quote_received",
                        {
                            "target": "A3:sber",
                            "message_type": "sber.procurement.quote.v1",
                            "supplier_id": agent.summary.supplier_id,
                            "quote_id": str(result.quote_id),
                            "payload_summary": {
                                "total_cost": str(result.total_cost),
                                "currency": result.currency,
                                "delivery_days": result.delivery_days,
                                "warranty_months": result.warranty_months,
                            },
                        },
                        actor=f"A2:{agent.summary.supplier_id}",
                    )
                )
        if len(quotes) < minimum_quotes:
            errors.append(
                f"Only {len(quotes)} supplier quotes received; "
                f"{minimum_quotes} required"
            )
        return {
            "quotes": [quote.model_dump(mode="json") for quote in quotes],
            "errors": errors,
            "events": [
                *events,
                _event(
                    "quotes_collected",
                    {
                        "target": "A3:sber",
                        "message_type": "sber.procurement.quote_batch.v1",
                        "requested": len(agents),
                        "received": len(quotes),
                    },
                )
            ],
        }

    def route_after_quotes(state: WorkflowState) -> Literal["rank", "finalize"]:
        return "finalize" if state["errors"] or not state["quotes"] else "rank"

    async def rank(state: WorkflowState) -> dict:
        intent = ProcurementIntent.model_validate(state["intent"])
        mandate = Mandate.model_validate(state["mandate"])
        quotes = []
        for item in state["quotes"]:
            quote = Quote.model_validate(item)
            trusted_risk = await risk_gateway.get_risk(quote.supplier_id)
            quotes.append(
                quote.model_copy(update={"supplier_risk": trusted_risk})
            )
        comparison = compare_quotes(quotes, intent, mandate)
        errors = list(state["errors"])
        if comparison.recommended_quote_id is None:
            errors.append("No quote passed the hard constraints")
        return {
            "quotes": [quote.model_dump(mode="json") for quote in quotes],
            "comparison": comparison.model_dump(mode="json"),
            "errors": errors,
            "events": state["events"]
            + [
                _event(
                    "quotes_ranked",
                    {
                        "target": "A1:client",
                        "message_type": "sber.procurement.comparison.v1",
                        "eligible": sum(
                            item.eligible for item in comparison.evaluated_quotes
                        ),
                        "recommended_quote_id": (
                            str(comparison.recommended_quote_id)
                            if comparison.recommended_quote_id
                            else None
                        ),
                    },
                )
            ],
        }

    async def explain(state: WorkflowState) -> dict:
        comparison = Comparison.model_validate(state["comparison"])
        explanation = await llm.explain_comparison(comparison)
        comparison = comparison.model_copy(update={"explanation": explanation})
        return {
            "comparison": comparison.model_dump(mode="json"),
            "events": state["events"]
            + [
                _event(
                    "comparison_explained",
                    {
                        "target": "A1:client",
                        "message_type": "sber.procurement.explanation.v1",
                        "llm_used": llm.enabled,
                    },
                )
            ],
        }

    def route_after_ranking(state: WorkflowState) -> Literal["explain", "finalize"]:
        comparison = state.get("comparison")
        return (
            "explain"
            if comparison and comparison.get("recommended_quote_id")
            else "finalize"
        )

    async def finalize(state: WorkflowState) -> dict:
        successful = (
            not state["errors"]
            and state.get("comparison") is not None
            and state["comparison"].get("recommended_quote_id") is not None
        )
        status = (
            DealStatus.AWAITING_APPROVAL
            if successful
            else DealStatus.FAILED
        )
        return {
            "status": status.value,
            "events": state["events"]
            + [
                _event(
                    "workflow_completed",
                    {
                        "target": "A1:client",
                        "message_type": "sber.procurement.workflow_status.v1",
                        "status": status.value,
                    },
                )
            ],
        }

    builder = StateGraph(WorkflowState)
    builder.add_node("validate", validate_mandate)
    builder.add_node("discover", discover_suppliers)
    builder.add_node("request_quotes", request_quotes)
    builder.add_node("rank", rank)
    builder.add_node("explain", explain)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "validate")
    builder.add_conditional_edges("validate", route_after_validation)
    builder.add_conditional_edges("discover", route_after_discovery)
    builder.add_conditional_edges("request_quotes", route_after_quotes)
    builder.add_conditional_edges("rank", route_after_ranking)
    builder.add_edge("explain", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=InMemorySaver())
