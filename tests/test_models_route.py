from fastapi.testclient import TestClient

from backend.app import create_app
from backend.routes import models


def test_models_route_returns_available_models() -> None:
    """Models route returns the list of available models."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/v1/models")

    assert resp.status_code == 200
    expected = {"data": [{"id": name, "object": "model"} for name in models.MODEL_NAMES]}
    assert resp.json() == expected
