import pytest
from httpx import ASGITransport, AsyncClient

from sber_a2a.api import create_app
from sber_a2a.config import Settings
from sber_a2a.container import build_container


async def test_a3_agent_card_contract(container) -> None:
    app = create_app(container)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/.well-known/agent-card.json")

    card = response.json()
    assert response.status_code == 200
    assert card["name"] == "Sber A3 Procurement Agent"
    assert card["defaultInputModes"] == ["application/json"]
    assert any(
        interface["protocolBinding"] == "JSONRPC"
        and interface["url"].endswith("/a2a")
        for interface in card["supportedInterfaces"]
    )
    assert {"procurement-rfq", "quote-comparison"} <= {
        skill["id"] for skill in card["skills"]
    }


async def test_demo_identity_header_is_required_for_approval(deal_request) -> None:
    container = build_container(
        Settings(
            llm_provider="disabled",
            database_url="sqlite+aiosqlite:///:memory:",
            demo_identity_enabled=True,
            _env_file=None,
        )
    )
    deal = await container.deals.create(deal_request)
    app = create_app(container)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/api/v1/deals/{deal.deal_id}/approve",
            json={
                "quote_id": str(deal.comparison.recommended_quote_id),
                "approved_by": "approver-1",
                "approval_snapshot_hash": deal.approval_snapshot.snapshot_hash,
            },
        )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"quote_id": "not-a-uuid", "approved_by": "approver-1"},
        {"quote_id": "00000000-0000-4000-8000-000000000001", "approved_by": "a"},
    ],
)
async def test_approval_contract_rejects_invalid_payload(
    container,
    deal_request,
    payload,
) -> None:
    deal = await container.deals.create(deal_request)
    app = create_app(container)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/api/v1/deals/{deal.deal_id}/approve",
            json=payload,
        )

    assert response.status_code == 422
