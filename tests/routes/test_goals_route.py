from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.common import goals as goals_mod
from backend.common.storage import get_storage


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
