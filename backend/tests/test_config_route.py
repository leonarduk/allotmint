from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import config as routes_config


def _setup_config(monkeypatch, tmp_path: Path, content: str = "auth:\n  google_auth_enabled: false\n") -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(content)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config.config_module, "_project_config_path", lambda: config_path)
    routes_config.config_module.load_config.cache_clear()
    routes_config.config_module.reload_config()
    return config_path


def test_put_config_with_env_missing_client_id_preserves_config(monkeypatch, tmp_path):
    config_path = _setup_config(monkeypatch, tmp_path)

    app = FastAPI()
    app.include_router(routes_config.router)
    client = TestClient(app)

    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")

    response = client.put("/config", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["google_auth_enabled"] is False
    assert data["google_client_id"] is None

    persisted = yaml.safe_load(config_path.read_text())
    assert persisted["auth"]["google_auth_enabled"] is False
    assert "google_client_id" not in persisted["auth"]

    get_resp = client.get("/config")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data == data
