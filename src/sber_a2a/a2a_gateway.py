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

from sber_a2a.container import Container
from sber_a2a.domain.models import CreateDealRequest


def _now() -> Timestamp:
    value = Timestamp()
    value.GetCurrentTime()
    return value


def _data_part(payload: dict) -> Part:
    data = Struct()
    data.update(payload)
    return Part(
        data=Value(struct_value=data),
        media_type="application/json",
    )


class ProcurementExecutor(AgentExecutor):
    def __init__(self, container: Container) -> None:
        self._container = container

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        task_id = context.task_id or str(uuid4())
        context_id = context.context_id or str(uuid4())
        message = context.message
        if message is None:
            raise ValueError("A procurement request message is required")
        parts = [part.data for part in message.parts if part.HasField("data")]
        if not parts:
            raise ValueError("A structured CreateDealRequest part is required")
        payload = MessageToDict(parts[0], preserving_proto_field_name=True)
        request = CreateDealRequest.model_validate(payload)

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
        deal = await self._container.deals.submit(request)
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                artifact=Artifact(
                    artifact_id=str(uuid4()),
                    name="sber.procurement.deal.accepted.v1",
                    parts=[
                        _data_part(
                            {
                                "deal_id": str(deal.deal_id),
                                "status": deal.status.value,
                            }
                        )
                    ],
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


def attach_a3_a2a_routes(
    app: FastAPI,
    container: Container,
    *,
    public_url: str,
) -> None:
    card = AgentCard(
        name="Sber A3 Procurement Agent",
        description=(
            "Trusted procurement orchestrator between A1 clients "
            "and accredited A2 suppliers."
        ),
        supported_interfaces=[
            AgentInterface(
                url=f"{public_url.rstrip('/')}/a2a",
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            ),
            AgentInterface(
                url=public_url.rstrip("/"),
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
                name="Parallel supplier RFQ",
                description="Validate a mandate and collect supplier quotes.",
                tags=["procurement", "rfq", "mro"],
            ),
            AgentSkill(
                id="quote-comparison",
                name="Deterministic quote comparison",
                description="Apply hard constraints and deterministic ranking.",
                tags=["tco", "risk", "explainability"],
            ),
        ],
    )
    handler = DefaultRequestHandler(
        agent_executor=ProcurementExecutor(container),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url="/a2a"),
        rest_routes=create_rest_routes(handler),
    )
