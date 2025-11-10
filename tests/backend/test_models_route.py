from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import models


def test_models_route_returns_available_models():
    app = FastAPI()
    app.include_router(models.router)

    with TestClient(app) as client:
        resp = client.get("/v1/models")

    assert resp.status_code == 200
    expected = {
        "data": [{"id": name, "object": "model"} for name in models.MODEL_NAMES]
    }
    assert resp.json() == expected

