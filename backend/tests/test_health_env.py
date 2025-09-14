from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config


def test_health_env_variable(monkeypatch):
    monkeypatch.setattr(config, "app_env", "patched")
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["env"] == "patched"
