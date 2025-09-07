from fastapi.testclient import TestClient

from backend.app import create_app
from backend.routes import scenario as scenario_route


def _auth_client():
    app = create_app()
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_scenario_route():
    client = _auth_client()
    resp = client.get("/scenario?ticker=VWRL.L&pct=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        first = data[0]
        assert "owner" in first
        assert "baseline_total_value_gbp" in first
        assert "shocked_total_value_gbp" in first
        assert "delta_gbp" in first


def test_historical_scenario_route(monkeypatch):
    def fake_apply_historical_event(portfolio, event_id=None, date=None, horizons=None):
        horizons = horizons or [1]
        total = portfolio.get("total_value_estimate_gbp") or 0.0
        return {h: {"total_value_estimate_gbp": total} for h in horizons}

    monkeypatch.setattr(
        scenario_route, "apply_historical_event", fake_apply_historical_event
    )

    client = _auth_client()
    resp = client.get("/scenario/historical?event_id=test&horizons=1&horizons=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        first = data[0]
        assert "owner" in first
        assert "baseline_total_value_gbp" in first
        assert "horizons" in first
        first_horizon = next(iter(first["horizons"].values()))
        assert "shocked_total_value_gbp" in first_horizon
        assert "pct_change" in first_horizon
