from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx

from sber_a2a.domain.models import (
    AgentContractCheckResult,
    AgentContractStatus,
    AgentRegistration,
    AgentRegistrationStatus,
    CreateOrganizationRequest,
    Organization,
    ProcurementIntent,
    ProductRequest,
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
        checked_at = datetime.now(UTC)
        registration = AgentRegistration(
            organization_id=request.organization_id,
            agent_id=request.agent_id,
            endpoint_url=request.endpoint_url.rstrip("/"),
            categories=request.categories,
            hosting_mode=request.hosting_mode,
            status=AgentRegistrationStatus.PENDING,
            agent_card_snapshot=card,
            last_checked_at=checked_at,
        )
        result = await self._check_agent_contract(registration)
        if result.status is not AgentContractStatus.PASSED:
            raise ValueError(result.message)
        registration = registration.model_copy(
            update={
                "status": AgentRegistrationStatus.ACTIVE,
                "contract_status": result.status,
                "contract_error": None,
                "last_checked_at": result.checked_at,
            }
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
        if request.status is AgentRegistrationStatus.ACTIVE:
            card = await self._load_agent_card(updated.endpoint_url)
            updated = updated.model_copy(update={"agent_card_snapshot": card})
            result = await self._check_agent_contract(updated)
            if result.status is not AgentContractStatus.PASSED:
                raise ValueError(result.message)
            updated = updated.model_copy(
                update={
                    "contract_status": result.status,
                    "contract_error": None,
                    "last_checked_at": result.checked_at,
                }
            )
        await self._store.put_agent_registration(updated)
        if request.status is AgentRegistrationStatus.ACTIVE:
            self._registry.register(self._to_remote_agent(updated))
        else:
            self._registry.unregister(agent_id)
        return updated

    async def check_agent(self, agent_id: str) -> AgentContractCheckResult:
        registrations = await self._store.list_agent_registrations()
        registration = next(
            (item for item in registrations if item.agent_id == agent_id),
            None,
        )
        if registration is None:
            raise DealNotFoundError(agent_id)
        try:
            card = await self._load_agent_card(registration.endpoint_url)
            registration = registration.model_copy(update={"agent_card_snapshot": card})
            result = await self._check_agent_contract(registration)
        except (httpx.HTTPError, ValueError, TimeoutError) as exc:
            result = AgentContractCheckResult(
                agent_id=registration.agent_id,
                endpoint_url=registration.endpoint_url,
                status=AgentContractStatus.FAILED,
                message=str(exc),
            )
        updated = registration.model_copy(
            update={
                "contract_status": result.status,
                "contract_error": (
                    None if result.status is AgentContractStatus.PASSED else result.message
                ),
                "last_checked_at": result.checked_at,
            }
        )
        await self._store.put_agent_registration(updated)
        return result

    async def restore(self) -> None:
        for registration in await self._store.list_agent_registrations():
            if (
                registration.status is AgentRegistrationStatus.ACTIVE
                and registration.contract_status is AgentContractStatus.PASSED
            ):
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
        skills = card.get("skills") or []
        if not any(skill.get("id") == "procurement-rfq" for skill in skills):
            raise ValueError("Agent Card has no procurement-rfq skill")
        return card

    async def _check_agent_contract(
        self,
        registration: AgentRegistration,
    ) -> AgentContractCheckResult:
        intent = ProcurementIntent(
            customer_id="contract-check",
            product=ProductRequest(
                sku="BEARING-6205-2RS",
                name="Contract check item",
                category=next(iter(registration.categories), "mro.standardized"),
                quantity=1,
            ),
            delivery_city="Moscow",
            delivery_by=date.today() + timedelta(days=14),
            max_total=Decimal("100000.00"),
        )
        agent = self._to_remote_agent(registration)
        try:
            quote = await agent.create_quote(intent)
        except (httpx.HTTPError, TimeoutError, ValueError) as exc:
            return AgentContractCheckResult(
                agent_id=registration.agent_id,
                endpoint_url=registration.endpoint_url,
                status=AgentContractStatus.FAILED,
                message=f"A2A RFQ contract check failed: {exc}",
            )
        return AgentContractCheckResult(
            agent_id=registration.agent_id,
            endpoint_url=registration.endpoint_url,
            status=AgentContractStatus.PASSED,
            quote_received=quote is not None,
            message=(
                "A2A RFQ contract check passed with quote artifact"
                if quote is not None
                else "A2A RFQ contract check passed with no_quote artifact"
            ),
        )

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
