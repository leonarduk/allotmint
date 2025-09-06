from fastapi.testclient import TestClient

from backend.app import create_app


def test_trading_agent_signals_route(monkeypatch):
    fake_signals = [{"ticker": "AAA", "action": "BUY", "reason": "r", "ignored": True}]
    monkeypatch.setattr("backend.agent.trading_agent.run", lambda: fake_signals)
    app = create_app()
    with TestClient(app) as client:
        token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
        client.headers.update({"Authorization": f"Bearer {token}"})
        resp = client.get("/trading-agent/signals")
    assert resp.status_code == 200
    assert resp.json() == [{"ticker": "AAA", "action": "BUY", "reason": "r"}]
