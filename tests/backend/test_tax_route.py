from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import get_current_user
from backend.routes import tax


def _app():
    app = FastAPI()
    app.include_router(tax.router)
    app.dependency_overrides[get_current_user] = lambda: "alice"
    return TestClient(app)


def test_harvest():
    client = _app()
    payload = {
        "positions": [
            {"ticker": "ABC", "basis": 100.0, "price": 80.0},
            {"ticker": "XYZ", "basis": 100.0, "price": 120.0},
        ]
    }
    resp = client.post("/tax/harvest", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["trades"] == [{"ticker": "ABC", "loss": 20.0}]
