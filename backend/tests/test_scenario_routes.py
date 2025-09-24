from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.routes import scenario


def _client(monkeypatch, list_plots_return, build_map=None):
    app = FastAPI()
    app.include_router(scenario.router)
    monkeypatch.setattr("backend.routes.scenario.list_plots", lambda: list_plots_return)

    def build(owner):
        action = None
        if build_map:
            action = build_map.get(owner)
        if action == "error":
            raise FileNotFoundError
        return build_map.get(owner, {
            "total_value_estimate_gbp": 100.0,
            "accounts": []
        }) if build_map and owner in build_map else {
            "total_value_estimate_gbp": 100.0,
            "accounts": []
        }

    monkeypatch.setattr("backend.routes.scenario.build_owner_portfolio", build)
    monkeypatch.setattr(
        "backend.routes.scenario.apply_price_shock",
        lambda pf, ticker, pct: {"total_value_estimate_gbp": pf["total_value_estimate_gbp"] * (1 + pct)},
    )
    def fake_historical(pf, event_id=None, date=None, horizons=None):
        results = {}
        for h in horizons or []:
            results[h] = {"total_value_estimate_gbp": pf["total_value_estimate_gbp"] * (1 + h / 1000)}
        return results

    monkeypatch.setattr("backend.routes.scenario.apply_historical_event", fake_historical)
    return TestClient(app)


def test_run_scenario_basic(monkeypatch):
    client = _client(monkeypatch, [{"owner": "alice", "accounts": [1]}])
    resp = client.get("/scenario", params={"ticker": "ABC", "pct": 0.1})
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["owner"] == "alice"
    assert data[0]["delta_gbp"] == 10.0


def test_run_scenario_skips_missing_portfolio(monkeypatch):
    build_map = {"alice": "error"}
    client = _client(monkeypatch, [{"owner": "alice", "accounts": [1]}], build_map)
    resp = client.get("/scenario", params={"ticker": "ABC", "pct": 0.1})
    assert resp.status_code == 200
    assert resp.json() == []


def test_run_scenario_derives_baseline(monkeypatch):
    build_map = {
        "bob": {
            "accounts": [{"value_estimate_gbp": 50}, {"value_estimate_gbp": 70}],
        }
    }
    client = _client(monkeypatch, [{"owner": "bob", "accounts": [1]}], build_map)
    resp = client.get("/scenario", params={"ticker": "XYZ", "pct": 0.1})
    assert resp.status_code == 200
    data = resp.json()[0]
    assert data["baseline_total_value_gbp"] == 120
    assert data["delta_gbp"] == 12.0


def test_historical_scenario_parses_tokens(monkeypatch):
    client = _client(monkeypatch, [{"owner": "alice", "accounts": [1]}])
    resp = client.get(
        "/scenario/historical", params={"event_id": "evt", "horizons": "1d,1w"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["horizons"]["1d"]["shocked_total_value_gbp"] == pytest.approx(100.1)
    assert data[0]["horizons"]["1w"]["shocked_total_value_gbp"] == pytest.approx(100.7)
