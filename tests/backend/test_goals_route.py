import importlib
from datetime import date, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes as routes_pkg
from backend.common import goals as goals_mod
from backend.common.storage import get_storage
from backend.routes import goals as goals_route


def _app(tmp_path, monkeypatch, *, active_user: str | None = "alice", disable_auth: bool = False):
    storage = get_storage(f"file://{tmp_path / 'goals.json'}")
    storage.save({})
    monkeypatch.setattr(goals_mod, "_STORAGE", storage)
    history = get_storage(f"file://{tmp_path / 'goal_history.json'}")
    history.save({})
    monkeypatch.setattr(goals_mod, "_HISTORY_STORAGE", history)
    monkeypatch.setattr(routes_pkg.app_config, "disable_auth", disable_auth)
    module = importlib.reload(goals_route)
    monkeypatch.setattr(module, "DEMO_OWNER", "demo", raising=False)
    app = FastAPI()
    if active_user is not None:
        # Override before including router
        async def override_user():
            return active_user

        # Key the override on the dependency the reloaded route actually
        # uses. Other test modules reload backend.auth, which replaces
        # get_current_user; this module's import-time reference then no
        # longer matches, the override silently never applied, and these
        # tests failed whenever such a module ran first in the process.
        app.dependency_overrides[module.get_current_user] = override_user
    app.include_router(module.router)
    return TestClient(app)


def test_create_and_list(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch)
    payload = {"name": "Car", "target_amount": 1000, "target_date": date.today().isoformat()}
    assert client.post("/goals", json=payload).status_code == 200
    resp = client.get("/goals")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["name"] == "Car"


def test_goal_progress(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch)
    payload = {"name": "House", "target_amount": 5000, "target_date": date.today().isoformat()}
    client.post("/goals", json=payload)
    resp = client.get("/goals/House", params={"current_amount": 2500})
    assert resp.status_code == 200
    data = resp.json()
    assert round(data["progress"], 2) == 0.5
    assert any(t["action"] == "buy" for t in data["trades"])


def test_goal_progress_history_and_projection(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch)
    payload = {"name": "House", "target_amount": 2000, "target_date": "2030-06-30"}
    client.post("/goals", json=payload)

    unknown = client.get("/goals/House").json()
    assert unknown["progress"] is None
    assert unknown["projection"]["status"] == "insufficient_history"

    first = client.post("/goals/House/progress", json={"amount": 200, "on": "2026-01-01"})
    assert first.status_code == 200
    assert first.json()["projection"]["status"] == "insufficient_history"

    second = client.post("/goals/House/progress", json={"amount": 500, "on": "2026-03-02"}).json()
    assert second["progress"] == 0.25
    assert second["projection"]["status"] == "projected"
    assert second["projection"]["projected_date"] == "2026-12-27"

    # Without an amount the latest recorded one is used.
    detail = client.get("/goals/House").json()
    assert detail["current_amount"] == 500
    assert detail["projection"]["projected_date"] == "2026-12-27"

    # History follows a rename.
    client.put("/goals/House", json={**payload, "name": "Home"})
    assert client.get("/goals/Home").json()["projection"]["points"] == 2

    assert client.post("/goals/Missing/progress", json={"amount": 1}).status_code == 404
    assert client.post("/goals/Home/progress", json={"amount": -1}).status_code == 422


def test_rename_onto_existing_goal_is_rejected_and_keeps_both_histories(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch)
    for name in ("House", "Car"):
        client.post("/goals", json={"name": name, "target_amount": 2000, "target_date": "2030-06-30"})
    client.post("/goals/House/progress", json={"amount": 100, "on": "2026-01-01"})
    client.post("/goals/Car/progress", json={"amount": 300, "on": "2026-02-01"})

    resp = client.put("/goals/House", json={"name": "Car", "target_amount": 1, "target_date": "2031-01-01"})

    assert resp.status_code == 409
    assert [g["name"] for g in client.get("/goals").json()] == ["House", "Car"]
    assert goals_mod.load_goal_history("alice", "House") == [(date(2026, 1, 1), 100.0)]
    assert goals_mod.load_goal_history("alice", "Car") == [(date(2026, 2, 1), 300.0)]


def test_rename_repoints_goal_to_history_when_save_and_rollback_fail(tmp_path, monkeypatch):
    """Save fails once and the history rollback fails: the goal follows its history (#11184)."""
    client = _app(tmp_path, monkeypatch)
    goal = {"name": "House", "target_amount": 2000, "target_date": "2030-06-30"}
    client.post("/goals", json=goal)
    client.post("/goals/House/progress", json={"amount": 500, "on": "2026-01-01"})

    real_save, real_rename = goals_route.save_goals, goals_route.rename_goal_history
    calls = {"save": 0, "rename": 0}

    def flaky_save(owner, goals_list):
        calls["save"] += 1
        if calls["save"] == 1:
            raise OSError("transient write failure")
        real_save(owner, goals_list)

    def rename_without_rollback(owner, old, new):
        calls["rename"] += 1
        if calls["rename"] > 1:
            raise RuntimeError("rollback failed")
        real_rename(owner, old, new)

    monkeypatch.setattr(goals_route, "save_goals", flaky_save)
    monkeypatch.setattr(goals_route, "rename_goal_history", rename_without_rollback)

    resp = client.put("/goals/House", json={**goal, "name": "Home"})

    assert resp.status_code == 200
    assert calls == {"save": 2, "rename": 2}
    assert [g["name"] for g in client.get("/goals").json()] == ["Home"]
    detail = client.get("/goals/Home").json()
    assert detail["current_amount"] == 500
    assert detail["progress"] == 0.25
    assert detail["projection"]["points"] == 1


def test_future_dated_progress_is_rejected(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch)
    client.post("/goals", json={"name": "House", "target_amount": 2000, "target_date": "2030-06-30"})
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    assert client.post("/goals/House/progress", json={"amount": 1, "on": tomorrow}).status_code == 422
    assert client.post("/goals/House/progress", json={"amount": 1, "on": date.today().isoformat()}).status_code == 200
    assert [d for d, _ in goals_mod.load_goal_history("alice", "House")] == [date.today()]


def test_non_finite_amounts_are_rejected(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch)
    client.post("/goals", json={"name": "House", "target_amount": 2000, "target_date": "2030-06-30"})
    headers = {"Content-Type": "application/json"}

    for raw in ('{"amount": Infinity}', '{"amount": NaN}'):
        assert client.post("/goals/House/progress", content=raw, headers=headers).status_code == 422
    assert client.get("/goals/House", params={"current_amount": "inf"}).status_code == 422
    assert goals_mod.load_goal_history("alice", "House") == []


def test_update_and_delete(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch)
    payload = {"name": "Trip", "target_amount": 2000, "target_date": date.today().isoformat()}
    client.post("/goals", json=payload)
    upd = {"name": "Trip", "target_amount": 3000, "target_date": date.today().isoformat()}
    resp = client.put("/goals/Trip", json=upd)
    assert resp.status_code == 200
    resp = client.delete("/goals/Trip")
    assert resp.status_code == 200
    assert client.get("/goals").json() == []


def test_crud_without_auth(tmp_path, monkeypatch):
    client = _app(tmp_path, monkeypatch, active_user=None, disable_auth=True)

    payload = {
        "name": "DemoGoal",
        "target_amount": 1500,
        "target_date": date.today().isoformat(),
    }

    assert client.post("/goals", json=payload).status_code == 200

    resp = client.get("/goals")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "DemoGoal"
    assert [g.name for g in goals_mod.load_goals("demo")] == ["DemoGoal"]
    assert goals_mod.load_goals("alice") == []

    detail = client.get("/goals/DemoGoal", params={"current_amount": 300}).json()
    assert detail["name"] == "DemoGoal"

    update = {"name": "DemoGoal", "target_amount": 2000, "target_date": date.today().isoformat()}
    assert client.put("/goals/DemoGoal", json=update).status_code == 200
    assert client.delete("/goals/DemoGoal").status_code == 200

    # Storage should only contain demo data and nothing for other owners.
    assert goals_mod.load_goals("demo") == []
    assert goals_mod.load_goals("alice") == []
