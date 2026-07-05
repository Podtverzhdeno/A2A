import os
from uuid import uuid4

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
    create_rest_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types.a2a_pb2 import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Artifact,
    Part,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from fastapi import FastAPI
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct, Value
from google.protobuf.timestamp_pb2 import Timestamp

from sber_a2a.domain.models import ProcurementIntent
from sber_a2a.suppliers.mock import MockSupplierAgent, get_demo_agent


def _now() -> Timestamp:
    value = Timestamp()
    value.GetCurrentTime()
    return value


def _data_part(value: dict) -> Part:
    data = Struct()
    data.update(value)
    return Part(data=Value(struct_value=data), media_type="application/json")


class SupplierQuoteExecutor(AgentExecutor):
    def __init__(self, supplier: MockSupplierAgent) -> None:
        self._supplier = supplier

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        task_id = context.task_id or str(uuid4())
        context_id = context.context_id or str(uuid4())
        message = context.message
        if message is None:
            raise ValueError("A procurement intent message is required")
        data_parts = [part.data for part in message.parts if part.HasField("data")]
        if not data_parts:
            raise ValueError("A structured procurement intent part is required")

        intent_data = MessageToDict(data_parts[0], preserving_proto_field_name=True)
        intent = ProcurementIntent.model_validate(intent_data)
        await event_queue.enqueue_event(
            Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_WORKING,
                    timestamp=_now(),
                ),
                history=[message],
            )
        )

        quote = await self._supplier.create_quote(intent)
        artifact_payload = (
            {"status": "no_quote"}
            if quote is None
            else {
                "status": "quoted",
                "quote": quote.model_dump(mode="json"),
            }
        )
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                artifact=Artifact(
                    artifact_id=str(uuid4()),
                    name="sber.procurement.quote.v1",
                    parts=[_data_part(artifact_payload)],
                ),
                last_chunk=True,
            )
        )
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_COMPLETED,
                    timestamp=_now(),
                ),
            )
        )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_CANCELED,
                    timestamp=_now(),
                ),
            )
        )


def create_supplier_app(
    supplier_id: str | None = None,
    *,
    public_url: str | None = None,
) -> FastAPI:
    supplier_id = supplier_id or os.getenv("SUPPLIER_ID", "supplier-a")
    port = int(os.getenv("APP_PORT", "8201"))
    public_url = public_url or os.getenv(
        "PUBLIC_URL",
        f"http://127.0.0.1:{port}",
    )
    supplier = get_demo_agent(supplier_id)
    card = AgentCard(
        name=supplier.summary.name,
        description=f"Demo A2 supplier agent owned by {supplier.summary.name}",
        supported_interfaces=[
            AgentInterface(
                url=f"{public_url}/a2a",
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            ),
            AgentInterface(
                url=public_url,
                protocol_binding="HTTP+JSON",
                protocol_version="1.0",
            ),
        ],
        version="0.2.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id="procurement-rfq",
                name="Create supplier quote",
                description="Accept a structured RFQ and return a quote artifact.",
                tags=["procurement", "rfq", "mro"],
            )
        ],
    )
    handler = DefaultRequestHandler(
        agent_executor=SupplierQuoteExecutor(supplier),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = FastAPI(
        title=f"A2 Supplier Agent — {supplier.summary.name}",
        version="0.2.0",
    )

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "role": "A2",
            "supplier_id": supplier.summary.supplier_id,
        }

    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/a2a"),
        rest_routes=create_rest_routes(handler),
    )
    return app


def run() -> None:
    import uvicorn

    port = int(os.getenv("APP_PORT", "8201"))
    uvicorn.run(
        create_supplier_app(),
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=port,
    )


app = create_supplier_app()
