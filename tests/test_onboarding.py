from sber_a2a.domain.models import (
    AgentContractCheckResult,
    AgentContractStatus,
    CreateOrganizationRequest,
    RegisterSupplierAgentRequest,
)


async def test_organization_is_persisted_for_agent_onboarding(container) -> None:
    organization = await container.onboarding.create_organization(
        CreateOrganizationRequest(
            legal_name="Demo Supplier LLC",
            tax_id="7700000001",
            roles={"supplier"},
        )
    )

    organizations = await container.onboarding.list_organizations()

    assert organizations[0].organization_id == organization.organization_id
    assert organizations[0].status.value == "verified"


async def test_agent_onboarding_requires_passing_a2a_contract_check(
    container,
    monkeypatch,
) -> None:
    organization = await container.onboarding.create_organization(
        CreateOrganizationRequest(
            legal_name="External Supplier LLC",
            tax_id="7700000002",
            roles={"supplier"},
        )
    )

    async def load_card(_endpoint: str) -> dict:
        return {
            "name": "External Supplier Agent",
            "supportedInterfaces": [{"protocolBinding": "JSONRPC"}],
            "skills": [{"id": "procurement-rfq"}],
        }

    async def check_contract(registration):
        return AgentContractCheckResult(
            agent_id=registration.agent_id,
            endpoint_url=registration.endpoint_url,
            status=AgentContractStatus.PASSED,
            quote_received=True,
            message="ok",
        )

    monkeypatch.setattr(container.onboarding, "_load_agent_card", load_card)
    monkeypatch.setattr(container.onboarding, "_check_agent_contract", check_contract)

    registration = await container.onboarding.register_supplier(
        RegisterSupplierAgentRequest(
            organization_id=organization.organization_id,
            agent_id="external-a2",
            endpoint_url="http://external-a2:8204",
        )
    )

    assert registration.status.value == "active"
    assert registration.contract_status is AgentContractStatus.PASSED
    assert container.registry.get("external-a2") is not None


async def test_agent_onboarding_rejects_failed_a2a_contract_check(
    container,
    monkeypatch,
) -> None:
    organization = await container.onboarding.create_organization(
        CreateOrganizationRequest(
            legal_name="Broken Supplier LLC",
            tax_id="7700000003",
            roles={"supplier"},
        )
    )

    async def load_card(_endpoint: str) -> dict:
        return {
            "name": "Broken Supplier Agent",
            "supportedInterfaces": [{"protocolBinding": "JSONRPC"}],
            "skills": [{"id": "procurement-rfq"}],
        }

    async def check_contract(registration):
        return AgentContractCheckResult(
            agent_id=registration.agent_id,
            endpoint_url=registration.endpoint_url,
            status=AgentContractStatus.FAILED,
            message="A2A RFQ contract check failed",
        )

    monkeypatch.setattr(container.onboarding, "_load_agent_card", load_card)
    monkeypatch.setattr(container.onboarding, "_check_agent_contract", check_contract)

    try:
        await container.onboarding.register_supplier(
            RegisterSupplierAgentRequest(
                organization_id=organization.organization_id,
                agent_id="broken-a2",
                endpoint_url="http://broken-a2:8205",
            )
        )
    except ValueError as exc:
        assert "contract check failed" in str(exc)
    else:
        raise AssertionError("Expected failed contract check to reject onboarding")

    assert container.registry.get("broken-a2") is None
