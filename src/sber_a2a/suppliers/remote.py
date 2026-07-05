import asyncio
from uuid import uuid4

import httpx
from a2a.client import ClientCallContext, ClientConfig, ClientFactory
from a2a.types.a2a_pb2 import Message, Part, Role, SendMessageRequest
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct, Value

from sber_a2a.domain.models import ProcurementIntent, Quote, SupplierSummary


class RemoteSupplierAgent:
    def __init__(
        self,
        supplier_id: str,
        endpoint: str,
        *,
        name: str | None = None,
        categories: set[str] | None = None,
        timeout_seconds: float = 5.0,
        max_attempts: int = 2,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._summary = SupplierSummary(
            supplier_id=supplier_id,
            name=name or supplier_id,
            categories=categories or {"mro.standardized"},
        )

    @property
    def summary(self) -> SupplierSummary:
        return self._summary

    async def create_quote(self, intent: ProcurementIntent) -> Quote | None:
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                return await self._request_quote(intent)
            except (httpx.HTTPError, TimeoutError, ValueError) as exc:
                last_error = exc
                if attempt < self._max_attempts:
                    await asyncio.sleep(0.1 * attempt)
        assert last_error is not None
        raise last_error

    async def _request_quote(self, intent: ProcurementIntent) -> Quote | None:
        data = Struct()
        data.update(intent.model_dump(mode="json"))
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as http:
            factory = ClientFactory(
                ClientConfig(
                    streaming=False,
                    httpx_client=http,
                    supported_protocol_bindings=["JSONRPC"],
                )
            )
            client = await factory.create_from_url(self._endpoint)
            request = SendMessageRequest(
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
            quote_payload: dict | None = None
            async for response in client.send_message(
                request,
                context=ClientCallContext(timeout=self._timeout_seconds),
            ):
                if not response.HasField("task"):
                    continue
                for artifact in response.task.artifacts:
                    for part in artifact.parts:
                        if part.HasField("data"):
                            quote_payload = MessageToDict(
                                part.data,
                                preserving_proto_field_name=True,
                            )
            await client.close()

        if quote_payload is None:
            raise ValueError("Supplier returned no quote artifact")
        if quote_payload.get("status") == "no_quote":
            return None
        return Quote.model_validate(quote_payload["quote"])
