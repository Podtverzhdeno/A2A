from datetime import UTC, datetime

import httpx

from sber_a2a.domain.models import (
    AgentRegistration,
    AgentRegistrationStatus,
    CreateOrganizationRequest,
    Organization,
    RegisterSupplierAgentRequest,
    UpdateAgentStatusRequest,
)
from sber_a2a.services.store import DealNotFoundError, SQLAlchemyDealStore
from sber_a2a.suppliers.mock import SupplierRegistry
from sber_a2a.suppliers.remote import RemoteSupplierAgent


class AgentOnboardingService:
    def __init__(
        self,
        store: SQLAlchemyDealStore,
        registry: SupplierRegistry,
        *,
        timeout_seconds: float,
        max_attempts: int,
    ) -> None:
        self._store = store
        self._registry = registry
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts

    async def create_organization(
        self,
        request: CreateOrganizationRequest,
    ) -> Organization:
        organization = Organization(**request.model_dump())
        await self._store.put_organization(organization)
        return organization

    async def list_organizations(self) -> list[Organization]:
        return await self._store.list_organizations()

    async def register_supplier(
        self,
        request: RegisterSupplierAgentRequest,
    ) -> AgentRegistration:
        await self._store.get_organization(request.organization_id)
        card = await self._load_agent_card(request.endpoint_url)
        registration = AgentRegistration(
            organization_id=request.organization_id,
            agent_id=request.agent_id,
            endpoint_url=request.endpoint_url.rstrip("/"),
            categories=request.categories,
            hosting_mode=request.hosting_mode,
            status=AgentRegistrationStatus.ACTIVE,
            agent_card_snapshot=card,
            last_checked_at=datetime.now(UTC),
        )
        await self._store.put_agent_registration(registration)
        self._registry.register(self._to_remote_agent(registration))
        return registration

    async def list_agents(self) -> list[AgentRegistration]:
        return await self._store.list_agent_registrations()

    async def update_agent_status(
        self,
        agent_id: str,
        request: UpdateAgentStatusRequest,
    ) -> AgentRegistration:
        registrations = await self._store.list_agent_registrations()
        registration = next(
            (item for item in registrations if item.agent_id == agent_id),
            None,
        )
        if registration is None:
            raise DealNotFoundError(agent_id)
        updated = registration.model_copy(update={"status": request.status})
        await self._store.put_agent_registration(updated)
        if request.status is AgentRegistrationStatus.ACTIVE:
            self._registry.register(self._to_remote_agent(updated))
        else:
            self._registry.unregister(agent_id)
        return updated

    async def restore(self) -> None:
        for registration in await self._store.list_agent_registrations():
            if registration.status is AgentRegistrationStatus.ACTIVE:
                self._registry.register(self._to_remote_agent(registration))

    async def _load_agent_card(self, endpoint: str) -> dict:
        card_url = f"{endpoint.rstrip('/')}/.well-known/agent-card.json"
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.get(card_url)
            response.raise_for_status()
            card = response.json()
        if not card.get("name"):
            raise ValueError("Agent Card has no name")
        interfaces = card.get("supportedInterfaces") or card.get(
            "supported_interfaces"
        )
        if not interfaces:
            raise ValueError("Agent Card has no supported interfaces")
        return card

    def _to_remote_agent(
        self,
        registration: AgentRegistration,
    ) -> RemoteSupplierAgent:
        return RemoteSupplierAgent(
            registration.agent_id,
            registration.endpoint_url,
            name=registration.agent_card_snapshot.get(
                "name",
                registration.agent_id,
            ),
            categories=registration.categories,
            timeout_seconds=self._timeout_seconds,
            max_attempts=self._max_attempts,
        )
