import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_rebalance_route(monkeypatch):
    sample_actual = {"AAA": 100.0, "BBB": 50.0}
    sample_target = {"AAA": 0.6, "BBB": 0.4}
    expected = [
        {"ticker": "AAA", "action": "buy", "amount": 10.0},
        {"ticker": "BBB", "action": "sell", "amount": 10.0},
    ]

    def fake_suggest(actual, target):
        assert actual == sample_actual
        assert target == sample_target
        return expected

    monkeypatch.setattr("backend.common.rebalance.suggest_trades", fake_suggest)

    from backend.routes import rebalance as rebalance_route

    app = FastAPI()
    app.include_router(rebalance_route.router)

    client = TestClient(app)
    resp = client.post("/rebalance", json={"actual": sample_actual, "target": sample_target})
    assert resp.status_code == 200

    data = [rebalance_route.TradeSuggestion(**item) for item in resp.json()]
    assert data == [rebalance_route.TradeSuggestion(**item) for item in expected]
