from datetime import date
import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes as routes_pkg
from backend.common import goals as goals_mod
from backend.common.storage import get_storage
from backend.routes import goals as goals_route
from backend.auth import get_current_user


def _app(tmp_path, monkeypatch, *, active_user: str | None = "alice", disable_auth: bool = False):
    storage = get_storage(f"file://{tmp_path / 'goals.json'}")
    storage.save({})
    monkeypatch.setattr(goals_mod, "_STORAGE", storage)
    monkeypatch.setattr(routes_pkg.app_config, "disable_auth", disable_auth)
    module = importlib.reload(goals_route)
    monkeypatch.setattr(module, "DEMO_OWNER", "demo", raising=False)
    app = FastAPI()
    app.include_router(module.router)
    if active_user is not None:
        app.dependency_overrides[get_current_user] = lambda: active_user
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
