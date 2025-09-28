import pytest
import sys

import yaml
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import reload_config
from backend.routes import config as routes_config



def _setup_config(monkeypatch, tmp_path, content: str = "auth:\n  google_auth_enabled: false\n"):
    """Write ``content`` to a temporary config file and patch paths."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(content)
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)
    reload_config()
    return config_path



def test_deep_merge_nested_dicts():
    dst = {"a": {"b": 1, "c": {"d": 2}}}
    src = {"a": {"b": 3, "c": {"e": 4}}, "f": 5}
    routes_config.deep_merge(dst, src)
    assert dst == {"a": {"b": 3, "c": {"d": 2, "e": 4}}, "f": 5}



def test_update_config_writes_and_merges(monkeypatch, tmp_path):
    config_path = _setup_config(monkeypatch, tmp_path, "tabs:\n  instrument: true\n")
    client = TestClient(create_app())

    resp = client.put("/config", json={"tabs": {"instrument": False, "support": False}})
    assert resp.status_code == 200

    data = yaml.safe_load(config_path.read_text())
    assert "tabs" not in data
    assert data["ui"]["tabs"]["instrument"] is False
    assert data["ui"]["tabs"]["support"] is False

    monkeypatch.undo()
    reload_config()



def test_update_config_env_invalid_google_auth(monkeypatch, tmp_path):
    _setup_config(monkeypatch, tmp_path)
    client = TestClient(create_app())
    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "maybe")

    resp = client.put("/config", json={})
    assert resp.status_code == 400
    assert "GOOGLE_AUTH_ENABLED" in resp.json()["detail"]

    monkeypatch.undo()
    reload_config()



def test_update_config_env_requires_client_id(monkeypatch, tmp_path):
    _setup_config(monkeypatch, tmp_path)
    client = TestClient(create_app())
    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")

    resp = client.put("/config", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "GOOGLE_CLIENT_ID is empty"

    monkeypatch.undo()
    reload_config()


def test_update_config_env_uses_existing_client_id(monkeypatch, tmp_path):
    _setup_config(
        monkeypatch,
        tmp_path,
        "auth:\n  google_auth_enabled: false\n  google_client_id: existing-id\n",
    )
    client = TestClient(create_app())
    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")

    resp = client.put("/config", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["google_auth_enabled"] is True
    assert data["google_client_id"] == "existing-id"

    get_resp = client.get("/config")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["google_auth_enabled"] is True
    assert get_data["google_client_id"] == "existing-id"

    monkeypatch.undo()
    reload_config()


def test_update_config_env_valid(monkeypatch, tmp_path):
    _setup_config(monkeypatch, tmp_path)
    client = TestClient(create_app())
    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")

    resp = client.put("/config", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["google_auth_enabled"] is True
    assert data["google_client_id"] == "client-id"

    get_resp = client.get("/config")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["google_auth_enabled"] is True
    assert get_data["google_client_id"] == "client-id"

    monkeypatch.undo()
    reload_config()
