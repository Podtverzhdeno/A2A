import os
from uuid import UUID, uuid4

import httpx
from a2a.client import ClientCallContext, ClientConfig, ClientFactory
from a2a.server.routes import add_a2a_routes_to_fastapi, create_agent_card_routes
from a2a.types.a2a_pb2 import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Message,
    Part,
    Role,
    SendMessageRequest,
)
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct, Value

from sber_a2a.domain.models import (
    ApprovalRequest,
    ApprovalResult,
    CreateDealRequest,
    DealRecord,
    SupplierSummary,
)


class A3ProcurementClient:
    def __init__(self, a3_url: str) -> None:
        self._a3_url = a3_url.rstrip("/")

    async def submit(self, request: CreateDealRequest) -> UUID:
        data = Struct()
        data.update(request.model_dump(mode="json"))
        async with httpx.AsyncClient(timeout=10) as http:
            factory = ClientFactory(
                ClientConfig(
                    streaming=False,
                    httpx_client=http,
                    supported_protocol_bindings=["JSONRPC"],
                )
            )
            client = await factory.create_from_url(self._a3_url)
            response = SendMessageRequest(
                message=Message(
                    message_id=str(uuid4()),
                    role=Role.ROLE_USER,
                    parts=[
                        Part(
                            data=Value(struct_value=data),
                            media_type="application/json",
                        )
                    ],
                )
            )
            result: dict | None = None
            async for item in client.send_message(
                response,
                context=ClientCallContext(timeout=10),
            ):
                if item.HasField("task"):
                    for artifact in item.task.artifacts:
                        for part in artifact.parts:
                            if part.HasField("data"):
                                result = MessageToDict(
                                    part.data,
                                    preserving_proto_field_name=True,
                                )
            await client.close()
        if result is None or "deal_id" not in result:
            raise ValueError("A3 returned no accepted deal artifact")
        return UUID(result["deal_id"])


def create_a1_app(a3_url: str | None = None) -> FastAPI:
    a3_url = a3_url or os.getenv("A3_URL", "http://127.0.0.1:8000")
    public_url = os.getenv("PUBLIC_URL", "http://127.0.0.1:8100")
    client = A3ProcurementClient(a3_url)
    app = FastAPI(
        title="A1 Customer Procurement Agent",
        version="0.2.0",
    )
    card = AgentCard(
        name="Demo A1 Customer Procurement Agent",
        description="Customer-side agent that submits procurement intents to A3.",
        supported_interfaces=[
            AgentInterface(
                url=public_url,
                protocol_binding="HTTP+JSON",
                protocol_version="1.0",
            )
        ],
        version="0.2.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id="procurement-intent",
                name="Submit procurement intent",
                description="Send a customer procurement intent to A3.",
                tags=["procurement", "buyer"],
            )
        ],
    )
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
    )

    @app.get("/health")
    async def health() -> dict:
        try:
            async with httpx.AsyncClient(timeout=3) as http:
                response = await http.get(f"{a3_url}/health")
                response.raise_for_status()
                a3_health = response.json()
        except httpx.HTTPError:
            return {
                "status": "degraded",
                "role": "A1",
                "llm_enabled": False,
                "llm_provider": "disabled",
                "a3_available": False,
            }
        return {
            **a3_health,
            "role": "A1 → A3",
            "a3_available": True,
        }

    @app.get("/api/v1/suppliers", response_model=list[SupplierSummary])
    async def suppliers() -> list[SupplierSummary]:
        async with httpx.AsyncClient(timeout=5) as http:
            response = await http.get(f"{a3_url}/api/v1/suppliers")
            response.raise_for_status()
            return [
                SupplierSummary.model_validate(item)
                for item in response.json()
            ]

    @app.post(
        "/api/v1/deals",
        response_model=DealRecord,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_deal(request: CreateDealRequest) -> DealRecord:
        try:
            deal_id = await client.submit(request)
            async with httpx.AsyncClient(timeout=5) as http:
                response = await http.get(f"{a3_url}/api/v1/deals/{deal_id}")
                response.raise_for_status()
                return DealRecord.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/v1/deals", response_model=list[DealRecord])
    async def list_deals() -> list[DealRecord]:
        async with httpx.AsyncClient(timeout=5) as http:
            response = await http.get(f"{a3_url}/api/v1/deals")
            response.raise_for_status()
            return [DealRecord.model_validate(item) for item in response.json()]

    @app.get("/api/v1/deals/{deal_id}", response_model=DealRecord)
    async def get_deal(deal_id: UUID) -> DealRecord:
        async with httpx.AsyncClient(timeout=5) as http:
            response = await http.get(f"{a3_url}/api/v1/deals/{deal_id}")
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Deal not found")
            response.raise_for_status()
            return DealRecord.model_validate(response.json())

    @app.post(
        "/api/v1/deals/{deal_id}/approve",
        response_model=ApprovalResult,
    )
    async def approve(
        deal_id: UUID,
        approval: ApprovalRequest,
        request: Request,
    ) -> ApprovalResult:
        identity = request.headers.get("X-Demo-User")
        headers = {"X-Demo-User": identity} if identity else {}
        async with httpx.AsyncClient(timeout=5) as http:
            response = await http.post(
                f"{a3_url}/api/v1/deals/{deal_id}/approve",
                json=approval.model_dump(mode="json"),
                headers=headers,
            )
            if response.status_code >= 400:
                detail = response.json().get("detail", response.text)
                raise HTTPException(response.status_code, detail=detail)
            return ApprovalResult.model_validate(response.json())

    @app.get(
        "/api/v1/deals/{deal_id}/events/stream",
        response_class=StreamingResponse,
    )
    async def stream_events(deal_id: UUID, request: Request) -> StreamingResponse:
        async def proxy():
            async with httpx.AsyncClient(timeout=None) as http:
                async with http.stream(
                    "GET",
                    f"{a3_url}/api/v1/deals/{deal_id}/events/stream",
                ) as response:
                    if response.status_code >= 400:
                        return
                    async for chunk in response.aiter_bytes():
                        if await request.is_disconnected():
                            return
                        yield chunk

        return StreamingResponse(proxy(), media_type="text/event-stream")

    return app


def run() -> None:
    import uvicorn

    uvicorn.run(
        create_a1_app(),
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "8100")),
    )


app = create_a1_app()
