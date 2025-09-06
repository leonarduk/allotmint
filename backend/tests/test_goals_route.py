from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import get_current_user
from backend.common.storage import get_storage
from backend.routes import goals as goals_route
from backend.common import goals as goals_mod


def _app(tmp_path, monkeypatch):
    storage = get_storage(f"file://{tmp_path / 'goals.json'}")
    storage.save({})
    monkeypatch.setattr(goals_mod, "_STORAGE", storage)
    app = FastAPI()
    app.include_router(goals_route.router)
    app.dependency_overrides[get_current_user] = lambda: "alice"
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
