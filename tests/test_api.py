import asyncio

from httpx import ASGITransport, AsyncClient

from sber_a2a.api import create_app
from sber_a2a.config import Settings
from sber_a2a.container import build_container


async def test_health_and_agent_card(container) -> None:
    app = create_app(container)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        health = await client.get("/health")
        card = await client.get("/.well-known/agent-card.json")

    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "role": "A3",
        "llm_enabled": False,
        "llm_provider": "disabled",
    }
    assert card.status_code == 200
    assert card.json()["name"] == "Sber A3 Procurement Agent"


async def test_agent_card_uses_configured_public_url() -> None:
    container = build_container(
        Settings(
            llm_provider="disabled",
            database_url="sqlite+aiosqlite:///:memory:",
            app_host="0.0.0.0",
            public_url="http://a3:8000",
            _env_file=None,
        )
    )
    app = create_app(container)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        card = await client.get("/.well-known/agent-card.json")

    interfaces = card.json()["supportedInterfaces"]
    assert interfaces[0]["url"] == "http://a3:8000/a2a"
    assert interfaces[1]["url"] == "http://a3:8000"


async def test_rest_deal_flow(container, deal_request) -> None:
    app = create_app(container)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/api/v1/deals",
            json=deal_request.model_dump(mode="json"),
        )
        assert created.status_code == 202
        payload = created.json()
        for _ in range(50):
            current = await client.get(f"/api/v1/deals/{payload['deal_id']}")
            payload = current.json()
            if payload["status"] != "draft":
                break
            await asyncio.sleep(0.01)

        approved = await client.post(
            f"/api/v1/deals/{payload['deal_id']}/approve",
            json={
                "quote_id": payload["comparison"]["recommended_quote_id"],
                "approved_by": "approver-1",
            },
        )
        evidence = await client.get(
            f"/api/v1/deals/{payload['deal_id']}/evidence"
        )
        history = await client.get("/api/v1/deals")

    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"
    assert evidence.status_code == 200
    assert evidence.json()["approval_snapshot"]["snapshot_hash"]
    assert evidence.json()["fulfillment"][-1]["status"] == "completed"
    assert len(evidence.json()["documents"]) == 3
    assert history.status_code == 200
    assert any(item["deal_id"] == payload["deal_id"] for item in history.json())


async def test_llm_endpoint_is_explicitly_unavailable_without_key(container) -> None:
    app = create_app(container)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/intents/parse",
            json={"text": "Купи 20 подшипников 6205-2RS с доставкой в Москву"},
        )

    assert response.status_code == 503
