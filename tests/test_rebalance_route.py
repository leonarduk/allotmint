import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.common.rebalance import suggest_trades


def test_rebalance_route():
    from backend.routes import rebalance as rebalance_route

    app = FastAPI()
    app.include_router(rebalance_route.router)
    client = TestClient(app)

    sample_actual = {"AAA": 100.0, "BBB": 50.0}
    sample_target = {"AAA": 0.6, "BBB": 0.4}

    resp = client.post("/rebalance", json={"actual": sample_actual, "target": sample_target})
    assert resp.status_code == 200
    assert resp.json() == [
        {"ticker": "AAA", "action": "sell", "amount": 10.0},
        {"ticker": "BBB", "action": "buy", "amount": 10.0},
    ]


def test_suggest_trades_valid_target_sum():
    actual = {"AAA": 100.0, "BBB": 50.0}
    target = {"AAA": 0.5, "BBB": 0.5}
    trades = suggest_trades(actual, target)
    assert trades == [
        {"ticker": "AAA", "action": "sell", "amount": 25.0},
        {"ticker": "BBB", "action": "buy", "amount": 25.0},
    ]


def test_suggest_trades_invalid_target_sum():
    actual = {"AAA": 100.0}
    target = {"AAA": 0.9}
    with pytest.raises(ValueError):
        suggest_trades(actual, target)


def test_rebalance_route_invalid_target_sum():
    from backend.routes import rebalance as rebalance_route

    app = FastAPI()
    app.include_router(rebalance_route.router)
    client = TestClient(app)

    resp = client.post("/rebalance", json={"actual": {"AAA": 100.0}, "target": {"AAA": 0.9}})
    assert resp.status_code == 400
