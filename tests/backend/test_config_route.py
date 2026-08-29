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


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes_config.router)
    return TestClient(app)


# Regression tests for the write-before-validate ordering bug. ``PUT /config``
# used to dump the merged document to config.yaml and only afterwards call
# reload_config(), which is what actually runs validate_tabs()/the rest of the
# validation. An invalid payload therefore got persisted first and rejected
# second, and because backend/config.py calls load_config() at import time the
# corrupted file then killed every subsequent backend start on any deployment
# where config.yaml is writable (local dev, docker). The fix validates the
# merged document before writing, so these assert both halves: a 400 *and* an
# untouched config.yaml that the backend can still boot from.
_VALID_CONFIG = "ui:\n  tabs:\n    market: true\n    reports: false\nauth:\n  google_auth_enabled: false\n"


def test_put_config_rejects_unknown_tab_without_writing(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    config_path = _setup_config(monkeypatch, tmp_path, _VALID_CONFIG)
    before = config_path.read_text()

    response = _client().put("/config", json={"tabs": {"not_a_real_tab": True}})

    assert response.status_code == 400
    assert "not_a_real_tab" in response.json()["detail"]

    # config.yaml must be byte-for-byte untouched...
    assert config_path.read_text() == before

    # ...and must still load, i.e. a fresh backend process would boot.
    routes_config.config_module.load_config.cache_clear()
    reloaded = routes_config.config_module.reload_config()
    assert reloaded.tabs.market is True
    assert reloaded.tabs.reports is False


def test_put_config_rejects_non_boolean_tab_without_writing(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    config_path = _setup_config(monkeypatch, tmp_path, _VALID_CONFIG)
    before = config_path.read_text()

    response = _client().put("/config", json={"tabs": {"market": "yes"}})

    assert response.status_code == 400
    assert config_path.read_text() == before


def test_put_config_rejects_non_boolean_feature_flag_without_writing(monkeypatch, tmp_path):
    # Not tab-specific: any key load_config() would reject must be caught
    # before the write, since the same corruption applies.
    monkeypatch.delenv("GOOGLE_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    config_path = _setup_config(monkeypatch, tmp_path, _VALID_CONFIG)
    before = config_path.read_text()

    response = _client().put("/config", json={"enable_family_mvp": "maybe"})

    assert response.status_code == 400
    assert config_path.read_text() == before


def test_put_config_still_persists_valid_tabs(monkeypatch, tmp_path):
    # Guard against the pre-validation over-rejecting: a legitimate tab
    # change must still be written and reloaded.
    monkeypatch.delenv("GOOGLE_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    config_path = _setup_config(monkeypatch, tmp_path, _VALID_CONFIG)

    response = _client().put("/config", json={"tabs": {"market": False}})

    assert response.status_code == 200
    persisted = yaml.safe_load(config_path.read_text())
    assert persisted["ui"]["tabs"]["market"] is False
    assert persisted["ui"]["tabs"]["reports"] is False
    assert response.json()["tabs"]["market"] is False
