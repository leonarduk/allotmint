import pytest
import yaml
from fastapi.testclient import TestClient

from backend import config as config_module
from backend.app import create_app
from backend.config import ConfigValidationError
from backend.routes import config as routes_config


def test_config_alias_settings():
    assert config_module.settings is config_module.config


def test_config_loads_fundamentals_ttl():
    cfg = config_module.load_config()
    assert cfg.fundamentals_cache_ttl_seconds == 86400


def test_tabs_defaults_true():
    cfg = config_module.load_config()
    assert cfg.tabs.instrument is True
    assert cfg.tabs.support is True
    assert cfg.tabs.movers is True
    assert cfg.tabs.group is True
    assert cfg.tabs.market is True
    assert cfg.tabs.owner is True
    assert cfg.tabs.allocation is True
    assert cfg.tabs.rebalance is True
    assert cfg.tabs.dataadmin is True
    assert cfg.tabs.instrumentadmin is True
    assert cfg.tabs.pension is True
    assert cfg.tabs.scenario is True


def test_theme_loaded():
    cfg = config_module.load_config()
    assert cfg.theme == "system"


def test_stooq_timeout_loaded():
    cfg = config_module.load_config()
    assert cfg.stooq_timeout == 10


def test_timeseries_cache_base_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    config_module.load_config.cache_clear()
    cfg = config_module.load_config()
    assert cfg.timeseries_cache_base == str(tmp_path)
    monkeypatch.delenv("TIMESERIES_CACHE_BASE")
    config_module.load_config.cache_clear()
    config_module.config = config_module.load_config()


def test_auth_flags(monkeypatch):
    cfg = config_module.load_config()
    assert cfg.google_auth_enabled is False
    assert cfg.disable_auth is True

    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client")
    monkeypatch.setenv("DISABLE_AUTH", "false")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client")
    config_module.load_config.cache_clear()
    cfg = config_module.load_config()
    assert cfg.google_auth_enabled is True
    assert cfg.disable_auth is False

    monkeypatch.delenv("GOOGLE_AUTH_ENABLED")
    monkeypatch.delenv("DISABLE_AUTH")
    monkeypatch.delenv("GOOGLE_CLIENT_ID")
    config_module.load_config.cache_clear()
    config_module.config = config_module.load_config()


def test_google_auth_requires_client_id(monkeypatch):
    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    config_module.load_config.cache_clear()
    with pytest.raises(ConfigValidationError):
        config_module.load_config()
    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "false")
    config_module.load_config.cache_clear()
    config_module.config = config_module.load_config()


def test_update_config_rejects_invalid_google_auth(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("auth:\n  google_auth_enabled: false\n")

    monkeypatch.setattr(config_module, "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    config_module.load_config.cache_clear()
    config_module.config = config_module.load_config()

    client = TestClient(create_app())

    resp = client.put("/config", json={"auth": {"google_auth_enabled": True}})
    assert resp.status_code == 400

    resp = client.put("/config", json={"google_auth_enabled": True})
    assert resp.status_code == 400

    config_module.load_config.cache_clear()
    cfg = config_module.load_config()
    assert cfg.google_auth_enabled is False
    config_module.config = cfg


def test_update_config_merges_ui_section(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("tabs:\n  instrument: true\n")

    monkeypatch.setattr(config_module, "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    config_module.load_config.cache_clear()
    config_module.config = config_module.load_config()

    client = TestClient(create_app())

    resp = client.put("/config", json={"ui": {"tabs": {"instrument": False}}})
    assert resp.status_code == 200

    data = yaml.safe_load(config_path.read_text())
    assert "tabs" not in data
    assert data["ui"]["tabs"]["instrument"] is False

    config_module.load_config.cache_clear()
    cfg = config_module.load_config()
    assert cfg.tabs.instrument is False
