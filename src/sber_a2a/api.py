import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from sber_a2a.a2a_gateway import attach_a3_a2a_routes
from sber_a2a.container import Container, build_container
from sber_a2a.domain.models import (
    AgentRegistration,
    ApprovalRequest,
    ApprovalResult,
    CreateDealRequest,
    CreateOrganizationRequest,
    DealEvent,
    DealRecord,
    DealStatus,
    EvidenceBundle,
    Organization,
    ParsedIntentDraft,
    ParseIntentRequest,
    RegisterSupplierAgentRequest,
    SupplierSummary,
    UpdateAgentStatusRequest,
)
from sber_a2a.mcp import create_mcp_server
from sber_a2a.services.deals import DealConflictError
from sber_a2a.services.llm import LLMUnavailableError
from sber_a2a.services.store import DealNotFoundError


def create_app(container: Container | None = None) -> FastAPI:
    container = container or build_container()
    mcp = create_mcp_server(container)
    mcp_app = mcp.http_app(path="/")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await container.onboarding.restore()
        await container.deals.resume_incomplete()
        async with mcp_app.lifespan(app):
            yield
        close = getattr(container.store, "close", None)
        if close is not None:
            await close()

    app = FastAPI(
        title=container.settings.app_name,
        version="0.1.0",
        description=(
            "A3 Sber orchestrator: A1 client → A3 Sber → multiple A2 suppliers."
        ),
        lifespan=lifespan,
    )
    app.state.container = container

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "role": "A3",
            "llm_enabled": container.llm.enabled,
            "llm_provider": container.llm.provider,
        }

    @app.get("/ready")
    async def ready() -> dict:
        checks: dict[str, bool | int] = {}
        try:
            await container.store.initialize()
            checks["database"] = True
        except Exception:
            checks["database"] = False
        suppliers = container.registry.list_suppliers()
        checks["active_suppliers"] = len(suppliers)
        ok = bool(checks["database"]) and len(suppliers) >= container.settings.minimum_quotes
        return {
            "status": "ready" if ok else "degraded",
            "role": "A3",
            "checks": checks,
        }

    @app.get("/api/v1/suppliers", response_model=list[SupplierSummary])
    async def list_suppliers() -> list[SupplierSummary]:
        return container.registry.list_suppliers()

    @app.post(
        "/api/v1/admin/organizations",
        response_model=Organization,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_organization(
        request: CreateOrganizationRequest,
    ) -> Organization:
        try:
            return await container.onboarding.create_organization(request)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get(
        "/api/v1/admin/organizations",
        response_model=list[Organization],
    )
    async def list_organizations() -> list[Organization]:
        return await container.onboarding.list_organizations()

    @app.post(
        "/api/v1/admin/agents",
        response_model=AgentRegistration,
        status_code=status.HTTP_201_CREATED,
    )
    async def register_supplier_agent(
        request: RegisterSupplierAgentRequest,
    ) -> AgentRegistration:
        try:
            return await container.onboarding.register_supplier(request)
        except DealNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail="Organization not found",
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get(
        "/api/v1/admin/agents",
        response_model=list[AgentRegistration],
    )
    async def list_registered_agents() -> list[AgentRegistration]:
        return await container.onboarding.list_agents()

    @app.patch(
        "/api/v1/admin/agents/{agent_id}/status",
        response_model=AgentRegistration,
    )
    async def update_registered_agent_status(
        agent_id: str,
        request: UpdateAgentStatusRequest,
    ) -> AgentRegistration:
        try:
            return await container.onboarding.update_agent_status(agent_id, request)
        except DealNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Agent not found") from exc

    @app.post(
        "/api/v1/deals",
        response_model=DealRecord,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_deal(request: CreateDealRequest) -> DealRecord:
        return await container.deals.submit(request)

    @app.get("/api/v1/deals", response_model=list[DealRecord])
    async def list_deals(
        limit: int = 50,
        offset: int = 0,
        deal_status: str | None = None,
    ) -> list[DealRecord]:
        return await container.deals.list(
            limit=min(max(limit, 1), 200),
            offset=max(offset, 0),
            status=deal_status,
        )

    @app.get("/api/v1/deals/{deal_id}", response_model=DealRecord)
    async def get_deal(deal_id: UUID) -> DealRecord:
        try:
            return await container.deals.get(deal_id)
        except DealNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Deal not found") from exc

    @app.get(
        "/api/v1/deals/{deal_id}/events",
        response_model=list[DealEvent],
    )
    async def get_deal_events(deal_id: UUID) -> list[DealEvent]:
        try:
            return (await container.deals.get(deal_id)).events
        except DealNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Deal not found") from exc

    @app.get(
        "/api/v1/deals/{deal_id}/evidence",
        response_model=EvidenceBundle,
    )
    async def get_deal_evidence(deal_id: UUID) -> EvidenceBundle:
        try:
            deal = await container.deals.get(deal_id)
        except DealNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Deal not found") from exc
        return EvidenceBundle(
            deal=deal,
            events=deal.events,
            approval_snapshot=deal.approval_snapshot,
            order=deal.order,
            payment_draft=deal.payment_draft,
            fulfillment=deal.fulfillment,
            documents=deal.documents,
            outbox_messages=(
                await container.store.list_outbox(deal_id)
                if hasattr(container.store, "list_outbox")
                else []
            ),
        )

    @app.get(
        "/api/v1/deals/{deal_id}/events/stream",
        response_class=StreamingResponse,
    )
    async def stream_deal_events(
        deal_id: UUID,
        after: int = 0,
    ) -> StreamingResponse:
        try:
            await container.deals.get(deal_id)
        except DealNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Deal not found") from exc

        async def generate():
            position = max(after, 0)
            while True:
                deal = await container.deals.get(deal_id)
                for sequence, event in enumerate(
                    deal.events[position:],
                    start=position + 1,
                ):
                    payload = event.model_dump(mode="json")
                    payload["sequence_number"] = sequence
                    yield (
                        f"id: {sequence}\n"
                        f"event: deal_event\n"
                        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    )
                    position = sequence
                if deal.status in {
                    DealStatus.AWAITING_APPROVAL,
                    DealStatus.ORDER_CREATED,
                    DealStatus.FULFILLING,
                    DealStatus.COMPLETED,
                    DealStatus.FAILED,
                }:
                    yield "event: stream_complete\ndata: {}\n\n"
                    return
                yield ": keep-alive\n\n"
                await asyncio.sleep(0.25)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post(
        "/api/v1/deals/{deal_id}/approve",
        response_model=ApprovalResult,
    )
    async def approve_deal(
        deal_id: UUID,
        request: ApprovalRequest,
        http_request: Request,
    ) -> ApprovalResult:
        if container.settings.demo_identity_enabled:
            identity = http_request.headers.get(
                container.settings.demo_identity_header
            )
            if not identity:
                raise HTTPException(
                    status_code=401,
                    detail="Demo identity header is required",
                )
            request = request.model_copy(update={"approved_by": identity})
        try:
            return await container.deals.approve(deal_id, request)
        except DealNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Deal not found") from exc
        except DealConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/intents/parse", response_model=ParsedIntentDraft)
    async def parse_intent(request: ParseIntentRequest) -> ParsedIntentDraft:
        try:
            return await container.llm.parse_intent(request.text)
        except LLMUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    frontend_index = frontend_dist / "index.html"
    frontend_assets = frontend_dist / "assets"

    if frontend_assets.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=frontend_assets),
            name="frontend-assets",
        )

    @app.get("/", include_in_schema=False, response_model=None)
    async def frontend() -> FileResponse | HTMLResponse:
        if frontend_index.is_file():
            return FileResponse(frontend_index)
        return HTMLResponse(
            "<h1>Frontend is not built</h1>"
            "<p>Run: cd frontend &amp;&amp; npm install &amp;&amp; npm run build</p>",
            status_code=503,
        )

    public_url = container.settings.public_url or (
        f"http://{container.settings.app_host}:{container.settings.app_port}"
    )
    attach_a3_a2a_routes(app, container, public_url=public_url)
    app.mount("/mcp", mcp_app, name="mcp")
    return app


app = create_app()
