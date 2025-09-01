import pytest
from httpx import AsyncClient, ASGITransport

from backend.app import create_app


@pytest.mark.asyncio
async def test_auth_alerts_portfolio(monkeypatch):
    app = create_app()
    monkeypatch.setattr(
        "backend.common.alerts.get_recent_alerts", lambda: [{"message": "hi"}]
    )
    monkeypatch.setattr(
        "backend.common.data_loader.list_plots",
        lambda root, current_user=None: [{"owner": "alice", "accounts": ["brokerage"]}],
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token_resp = await client.post(
            "/token", data={"username": "testuser", "password": "password"}
        )
        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        alerts_resp = await client.get("/alerts/", headers=headers)
        owners_resp = await client.get("/owners", headers=headers)
    assert token
    assert alerts_resp.status_code == 200
    assert owners_resp.status_code == 200
    assert owners_resp.json()[0]["owner"] == "alice"
