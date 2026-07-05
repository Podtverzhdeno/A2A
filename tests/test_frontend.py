from httpx import ASGITransport, AsyncClient

from sber_a2a.api import create_app


async def test_frontend_entrypoint(container) -> None:
    app = create_app(container)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/")

    assert response.status_code in {200, 503}
    if response.status_code == 200:
        assert "Sber A2A Control Room" in response.text
    else:
        assert "npm run build" in response.text
