from fastapi.testclient import TestClient
from pathlib import Path
import json

from backend.app import create_app
from backend.routes import scenario as scenario_route


def _auth_client():
    app = create_app()
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_scenario_route(monkeypatch):
    monkeypatch.setattr(
        scenario_route,
        "list_plots",
        lambda: [{"owner": "alice", "full_name": "Alice Example", "accounts": [{}]}],
    )
    monkeypatch.setattr(
        scenario_route,
        "build_owner_portfolio",
        lambda owner: {"total_value_estimate_gbp": 100.0, "accounts": []},
    )

    def fake_apply_price_shock(pf, ticker, pct):
        pf["total_value_estimate_gbp"] = 105.0
        return pf

    monkeypatch.setattr(scenario_route, "apply_price_shock", fake_apply_price_shock)

    client = _auth_client()
    resp = client.get("/scenario?ticker=VWRL.L&pct=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data == [
        {
            "owner": "alice",
            "baseline_total_value_gbp": 100.0,
            "shocked_total_value_gbp": 105.0,
            "delta_gbp": 5.0,
        }
    ]


def test_historical_scenario_route(monkeypatch):
    def fake_apply_historical_event(portfolio, event_id=None, date=None, horizons=None):
        horizons = horizons or [1]
        total = portfolio.get("total_value_estimate_gbp") or 0.0
        return {h: {"total_value_estimate_gbp": total} for h in horizons}

    monkeypatch.setattr(
        scenario_route, "apply_historical_event", fake_apply_historical_event
    )
    monkeypatch.setattr(
        scenario_route,
        "list_plots",
        lambda: [{"owner": "alice", "full_name": "Alice Example", "accounts": [{}]}],
    )
    monkeypatch.setattr(
        scenario_route,
        "build_owner_portfolio",
        lambda owner: {"total_value_estimate_gbp": 100.0, "accounts": []},
    )

    client = _auth_client()
    resp = client.get("/scenario/historical?event_id=test&horizons=1&horizons=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data == [
        {
            "owner": "alice",
            "baseline_total_value_gbp": 100.0,
            "horizons": {
                "1": {
                    "baseline_total_value_gbp": 100.0,
                    "shocked_total_value_gbp": 100.0,
                },
                "5": {
                    "baseline_total_value_gbp": 100.0,
                    "shocked_total_value_gbp": 100.0,
                },
            },
        }
    ]
    if data:
        first = data[0]
        assert "owner" in first
        assert "baseline_total_value_gbp" in first
        assert "horizons" in first
        first_horizon = next(iter(first["horizons"].values()))
        assert "baseline_total_value_gbp" in first_horizon
        assert "shocked_total_value_gbp" in first_horizon


def test_events_route():
    client = _auth_client()
    resp = client.get("/events")
    assert resp.status_code == 200
    data = resp.json()
    events_path = Path(__file__).resolve().parents[1] / "data" / "events.json"
    with events_path.open() as fh:
        expected = [{"id": e["id"], "name": e["name"]} for e in json.load(fh)]
    assert data == expected

