from sber_a2a.domain.models import CreateOrganizationRequest


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
