from datetime import date
from importlib import reload

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common import goals as goals_mod
from backend.common.storage import get_storage
from backend.config import config


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Return authenticated client with isolated goal storage."""
    storage = get_storage(f"file://{tmp_path / 'goals.json'}")
    storage.save({})
    monkeypatch.setattr(goals_mod, "_STORAGE", storage)

    app = create_app()
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_goal_crud_and_progress(client):
    payload = {
        "name": "House",
        "target_amount": 5000,
        "target_date": date.today().isoformat(),
    }
    # create
    resp = client.post("/goals", json=payload)
    assert resp.status_code == 200

    # list
    resp = client.get("/goals")
    assert resp.status_code == 200
    assert resp.json() == [payload]

    # retrieve with progress and trades
    resp = client.get("/goals/House", params={"current_amount": 2500})
    assert resp.status_code == 200
    data = resp.json()
    assert data["progress"] == pytest.approx(0.5)
    assert data["trades"] == [
        {"ticker": "cash", "action": "sell", "amount": 2500.0},
        {"ticker": "goal", "action": "buy", "amount": 2500.0},
    ]

    # update
    upd = {
        "name": "House",
        "target_amount": 6000,
        "target_date": date.today().isoformat(),
    }
    resp = client.put("/goals/House", json=upd)
    assert resp.status_code == 200
    assert client.get("/goals").json()[0]["target_amount"] == 6000

    # delete
    resp = client.delete("/goals/House")
    assert resp.status_code == 200
    assert client.get("/goals").json() == []


def test_goal_not_found(client):
    params = {"current_amount": 100}
    assert client.get("/goals/Unknown", params=params).status_code == 404

    payload = {
        "name": "Unknown",
        "target_amount": 1000,
        "target_date": date.today().isoformat(),
    }
    assert client.put("/goals/Unknown", json=payload).status_code == 404
    assert client.delete("/goals/Unknown").status_code == 404


def test_goals_router_demo_mode(monkeypatch, request):
    import backend.routes.goals as goals_module

    monkeypatch.setattr(config, "disable_auth", True)
    goals_module = reload(goals_module)

    def _restore() -> None:
        monkeypatch.undo()
        config.disable_auth = False
        reload(goals_module)

    request.addfinalizer(_restore)

    store = {
        goals_module.DEMO_OWNER: [
            goals_module.Goal("Initial", 1000.0, date(2024, 1, 1)),
        ]
    }
    calls: dict[str, list] = {"load": [], "add": [], "delete": [], "save": []}

    def fake_load(owner: str):
        calls["load"].append(owner)
        return list(store.get(owner, []))

    def fake_add(owner: str, goal):
        calls["add"].append((owner, goal))
        store.setdefault(owner, []).append(goal)

    def fake_delete(owner: str, name: str):
        calls["delete"].append((owner, name))
        store[owner] = [g for g in store.get(owner, []) if g.name != name]

    def fake_save(owner: str, goals):
        calls["save"].append((owner, list(goals)))
        store[owner] = list(goals)

    def fail_get_current_user(*args, **kwargs):  # pragma: no cover - safety guard
        pytest.fail("get_current_user should not be called when auth is disabled")

    monkeypatch.setattr(goals_module, "load_goals", fake_load)
    monkeypatch.setattr(goals_module, "add_goal", fake_add)
    monkeypatch.setattr(goals_module, "delete_goal", fake_delete)
    monkeypatch.setattr(goals_module, "save_goals", fake_save)
    monkeypatch.setattr(goals_module, "get_current_user", fail_get_current_user)

    app = FastAPI()
    app.include_router(goals_module.router)
    client = TestClient(app)

    initial_payload = [g.to_dict() for g in store[goals_module.DEMO_OWNER]]
    resp = client.get("/goals")
    assert resp.status_code == 200
    assert resp.json() == initial_payload

    new_payload = {
        "name": "Trip",
        "target_amount": 2000.0,
        "target_date": "2025-07-01",
    }
    resp = client.post("/goals", json=new_payload)
    assert resp.status_code == 200
    assert resp.json() == new_payload

    updated_payload = {
        "name": "Trip",
        "target_amount": 2500.0,
        "target_date": "2025-07-01",
    }
    resp = client.put("/goals/Trip", json=updated_payload)
    assert resp.status_code == 200
    assert resp.json() == updated_payload

    resp = client.delete("/goals/Trip")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}

    resp = client.get("/goals")
    assert resp.status_code == 200
    assert resp.json() == initial_payload

    assert calls["load"]
    assert set(calls["load"]) == {goals_module.DEMO_OWNER}
    assert calls["add"]
    assert {owner for owner, _ in calls["add"]} == {goals_module.DEMO_OWNER}
    assert calls["delete"]
    assert {owner for owner, _ in calls["delete"]} == {goals_module.DEMO_OWNER}
    assert calls["save"]
    assert {owner for owner, _ in calls["save"]} == {goals_module.DEMO_OWNER}
