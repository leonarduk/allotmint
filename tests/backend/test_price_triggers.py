from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import price_triggers as pt
from backend.auth import get_active_user, get_current_user
from backend.routes import price_triggers as routes


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("PRICE_TRIGGERS_URI", f"file://{tmp_path / 'triggers.json'}")
    monkeypatch.delenv("DATA_BUCKET", raising=False)
    fired = []
    monkeypatch.setattr(pt, "publish_alert", fired.append)
    return fired


def test_create_list_update_delete():
    row = pt.create_trigger("alice", ticker=" vod.l ", condition="ABOVE", price="1.5", mode="continuous")
    assert row["ticker"] == "VOD.L"
    assert row["condition"] == "above"
    assert row["price"] == 1.5
    assert pt.list_triggers("alice") == [row]
    assert pt.list_triggers("bob") == []
    assert pt.list_triggers("alice", ticker="AZN.L") == []

    updated = pt.update_trigger("alice", row["id"], price=2, note="  trim  ")
    assert updated["price"] == 2.0
    assert updated["note"] == "trim"

    pt.delete_trigger("alice", row["id"])
    assert pt.list_triggers("alice") == []
    with pytest.raises(pt.TriggerNotFound):
        pt.delete_trigger("alice", row["id"])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ticker": "", "condition": "above", "price": 1},
        {"ticker": "X", "condition": "sideways", "price": 1},
        {"ticker": "X", "condition": "above", "price": 0},
        {"ticker": "X", "condition": "above", "price": "nan"},
        {"ticker": "X", "condition": "above", "price": "abc"},
        {"ticker": "X", "condition": "above", "price": 1, "mode": "sometimes"},
    ],
)
def test_create_rejects_invalid(kwargs):
    with pytest.raises(pt.TriggerError):
        pt.create_trigger("alice", **kwargs)


def test_update_rejects_unknown_and_empty():
    row = pt.create_trigger("alice", ticker="X", condition="above", price=1)
    with pytest.raises(pt.TriggerError):
        pt.update_trigger("alice", row["id"], owner="bob")
    with pytest.raises(pt.TriggerError):
        pt.update_trigger("alice", row["id"])
    with pytest.raises(pt.TriggerNotFound):
        pt.update_trigger("bob", row["id"], price=2)


def test_per_user_limit(monkeypatch):
    monkeypatch.setattr(pt, "MAX_TRIGGERS_PER_USER", 1)
    pt.create_trigger("alice", ticker="X", condition="above", price=1)
    with pytest.raises(pt.TriggerError, match="limit"):
        pt.create_trigger("alice", ticker="Y", condition="above", price=1)
    pt.create_trigger("bob", ticker="Y", condition="above", price=1)


def test_once_fires_a_single_time(store):
    row = pt.create_trigger("alice", ticker="VOD.L", condition="above", price=1.0, mode="once")
    assert pt.evaluate({"VOD.L": 0.9}) == []
    assert len(pt.evaluate({"VOD.L": 1.0})) == 1
    assert pt.evaluate({"VOD.L": 0.5}) == []
    assert pt.evaluate({"VOD.L": 1.2}) == []
    saved = pt.get_trigger("alice", row["id"])
    assert saved["enabled"] is False
    assert saved["trigger_count"] == 1
    assert saved["last_triggered_price"] == 1.0
    assert len(store) == 1
    assert store[0]["user"] == "alice"
    assert "VOD.L" in store[0]["message"]


def test_continuous_fires_on_each_crossing_not_each_refresh(store):
    pt.create_trigger("alice", ticker="VOD.L", condition="below", price=1.0, mode="continuous")
    assert len(pt.evaluate({"VOD.L": 0.9})) == 1
    assert pt.evaluate({"VOD.L": 0.8}) == []  # still below: no repeat
    assert pt.evaluate({"VOD.L": 1.1}) == []  # back above: re-arms
    assert len(pt.evaluate({"VOD.L": 0.95})) == 1
    assert pt.list_triggers("alice")[0]["trigger_count"] == 2
    assert pt.list_triggers("alice")[0]["enabled"] is True


def test_missing_prices_neither_fire_nor_rearm():
    row = pt.create_trigger("alice", ticker="VOD.L", condition="above", price=1.0, mode="continuous")
    assert len(pt.evaluate({"VOD.L": 2.0})) == 1
    assert pt.evaluate({"VOD.L": None, "OTHER": 5}) == []
    assert pt.evaluate({"VOD.L": float("nan")}) == []
    assert pt.evaluate({"VOD.L": 3.0}) == []  # never saw it drop back: still disarmed
    assert pt.get_trigger("alice", row["id"])["armed"] is False


def test_disabled_trigger_is_ignored_and_amend_rearms(store):
    row = pt.create_trigger("alice", ticker="VOD.L", condition="above", price=1.0, enabled=False)
    assert pt.evaluate({"VOD.L": 2.0}) == []
    assert pt.watched_tickers() == []
    pt.update_trigger("alice", row["id"], enabled=True)
    assert pt.watched_tickers() == ["VOD.L"]
    assert len(pt.evaluate({"VOD.L": 2.0})) == 1
    # a spent "once" trigger fires again after being re-enabled
    pt.update_trigger("alice", row["id"], enabled=True)
    assert len(pt.evaluate({"VOD.L": 2.0})) == 1


def test_publish_failure_does_not_lose_other_alerts(monkeypatch):
    calls = []

    def flaky(alert):
        calls.append(alert)
        if len(calls) == 1:
            raise RuntimeError("sns down")

    monkeypatch.setattr(pt, "publish_alert", flaky)
    pt.create_trigger("alice", ticker="A", condition="above", price=1)
    pt.create_trigger("alice", ticker="B", condition="above", price=1)
    assert len(pt.evaluate({"A": 2, "B": 2})) == 2
    assert len(calls) == 2


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_active_user] = lambda: "alice"
    app.dependency_overrides[get_current_user] = lambda: "alice"
    return TestClient(app)


def test_routes_crud(client):
    r = client.post("/price-triggers/alice", json={"ticker": "vod.l", "condition": "above", "price": 1.5})
    assert r.status_code == 201
    tid = r.json()["id"]
    assert r.json()["mode"] == "once"

    assert [t["id"] for t in client.get("/price-triggers/alice").json()] == [tid]

    r = client.patch(f"/price-triggers/alice/{tid}", json={"price": 2.5, "mode": "continuous"})
    assert r.status_code == 200
    assert (r.json()["price"], r.json()["mode"]) == (2.5, "continuous")

    assert client.delete(f"/price-triggers/alice/{tid}").json()["status"] == "deleted"
    assert client.delete(f"/price-triggers/alice/{tid}").status_code == 404


def test_routes_validation_and_ownership(client):
    assert client.post("/price-triggers/alice", json={"ticker": "X", "condition": "up", "price": 1}).status_code == 422
    assert client.post("/price-triggers/alice", json={"ticker": "X", "condition": "above", "price": -1}).status_code == 422
    assert client.get("/price-triggers/bob").status_code == 403
    assert client.patch("/price-triggers/alice/nope", json={"price": 1}).status_code == 404
