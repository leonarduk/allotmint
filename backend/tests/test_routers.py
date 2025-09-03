import importlib
import pkgutil

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

import backend.routes as routes_pkg
from backend.routes import compliance, trading_agent


def test_all_routes_registered():
    missing = []
    for _, name, _ in pkgutil.iter_modules(routes_pkg.__path__):
        module = importlib.import_module(f"backend.routes.{name}")
        router = getattr(module, "router", None)
        if not isinstance(router, APIRouter) or not router.routes:
            missing.append(name)
    assert not missing, f"Routers missing routes: {missing}"


def test_compliance_routes(monkeypatch):
    app = FastAPI()
    app.state.accounts_root = ""
    app.include_router(compliance.router)

    monkeypatch.setattr(
        "backend.common.compliance.check_owner",
        lambda owner, root: {"owner": owner, "warnings": []},
    )
    with TestClient(app) as client:
        resp = client.get("/compliance/alice")
    assert resp.status_code == 200
    assert resp.json()["owner"] == "alice"

    monkeypatch.setattr(
        "backend.common.compliance.check_trade",
        lambda trade, root: {"warnings": ["ok"]},
    )
    with TestClient(app) as client:
        resp2 = client.post("/compliance/validate", json={"owner": "alice"})
        resp3 = client.post("/compliance/validate", json={})
    assert resp2.status_code == 200
    assert resp2.json()["warnings"] == ["ok"]
    assert resp3.status_code == 422


def test_trading_agent_route(monkeypatch):
    app = FastAPI()
    app.include_router(trading_agent.router)

    monkeypatch.setattr(
        "backend.agent.trading_agent.run",
        lambda: [{"ticker": "AAA", "action": "BUY"}],
    )
    with TestClient(app) as client:
        resp = client.get("/trading-agent/signals")
    assert resp.status_code == 200
    assert resp.json() == [{"ticker": "AAA", "action": "BUY"}]


def test_agent_stats_route(monkeypatch):
    fake_metrics = {"win_rate": 0.5, "average_profit": 1.23}
    monkeypatch.setattr("backend.common.trade_metrics.load_and_compute_metrics", lambda: fake_metrics)
    agent = importlib.import_module("backend.routes.agent")
    importlib.reload(agent)
    app = FastAPI()
    app.include_router(agent.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/agent/stats")
    assert resp.status_code == 200
    assert resp.json() == fake_metrics


def test_agent_stats_route_error(monkeypatch):
    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr("backend.common.trade_metrics.load_and_compute_metrics", boom)
    agent = importlib.import_module("backend.routes.agent")
    importlib.reload(agent)
    app = FastAPI()
    app.include_router(agent.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/agent/stats")
    assert resp.status_code == 500
    assert resp.text == "Internal Server Error"
