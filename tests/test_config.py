import sys

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import (
    ConfigValidationError,
    _project_config_path,
    config,
    demo_identity,
    local_login_identity,
    reload_config,
    settings,
    smoke_identity,
)
from backend.routes import config as routes_config


def test_config_alias_settings():
    assert settings is config


def test_config_loads_fundamentals_ttl():
    cfg = reload_config()
    assert cfg.fundamentals_cache_ttl_seconds == 86400


def test_tabs_defaults_true():
    cfg = reload_config()
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
    cfg = reload_config()
    assert cfg.theme == "system"


def test_family_mvp_flags_default_when_missing(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("ui:\n  theme: dark\n")
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    cfg = reload_config()
    try:
        assert cfg.enable_family_mvp is True
        assert cfg.enable_compliance_workflows is False
        assert cfg.enable_advanced_analytics is False
        assert cfg.enable_reporting_extended is False
    finally:
        monkeypatch.undo()
        reload_config()


def test_family_mvp_flag_none_falls_back_to_default(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("ui:\n  enable_family_mvp: null\n")
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    cfg = reload_config()
    try:
        assert cfg.enable_family_mvp is True
    finally:
        monkeypatch.undo()
        reload_config()


def test_family_mvp_flags_load_from_ui_section(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "ui:\n"
        "  enable_family_mvp: false\n"
        "  enable_compliance_workflows: true\n"
        "  enable_advanced_analytics: true\n"
        "  enable_reporting_extended: true\n",
    )
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    cfg = reload_config()
    try:
        assert cfg.enable_family_mvp is False
        assert cfg.enable_compliance_workflows is True
        assert cfg.enable_advanced_analytics is True
        assert cfg.enable_reporting_extended is True
    finally:
        monkeypatch.undo()
        reload_config()


def test_stooq_timeout_loaded():
    cfg = reload_config()
    assert cfg.stooq_timeout == 10


def test_timeseries_cache_base_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cfg = reload_config()
    assert cfg.timeseries_cache_base == str(tmp_path)
    monkeypatch.delenv("TIMESERIES_CACHE_BASE")
    reload_config()


def test_auth_flags(monkeypatch):
    cfg = reload_config()
    assert cfg.google_auth_enabled is False
    assert cfg.disable_auth is True

    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client")
    monkeypatch.setenv("DISABLE_AUTH", "false")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client")
    cfg = reload_config()
    assert cfg.google_auth_enabled is True
    assert cfg.disable_auth is False

    monkeypatch.delenv("GOOGLE_AUTH_ENABLED")
    monkeypatch.delenv("DISABLE_AUTH")
    monkeypatch.delenv("GOOGLE_CLIENT_ID")
    reload_config()


def test_demo_identity_override(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("auth:\n  demo_identity: steve\n")

    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    cfg = reload_config()
    try:
        assert cfg.demo_identity == "steve"
        assert demo_identity() == "steve"
        assert cfg.smoke_identity == "steve"
        assert smoke_identity() == "steve"
    finally:
        monkeypatch.undo()
        reload_config()


def test_smoke_identity_override(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("auth:\n  demo_identity: steve\n  smoke_identity: rachel\n")

    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    cfg = reload_config()
    try:
        assert cfg.demo_identity == "steve"
        assert cfg.smoke_identity == "rachel"
        assert demo_identity() == "steve"
        assert smoke_identity() == "rachel"
    finally:
        monkeypatch.undo()
        reload_config()


def test_local_login_email_override(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("auth:\n  local_login_email: user@example.com\n")

    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    cfg = reload_config()
    try:
        assert cfg.local_login_email == "user@example.com"
        assert local_login_identity() == "user@example.com"
    finally:
        monkeypatch.undo()
        reload_config()


def test_allowed_emails_loaded_lowercase():
    raw = yaml.safe_load(_project_config_path().read_text())["auth"]["allowed_emails"]
    emails = raw if isinstance(raw, list) else [raw]
    expected = [email.lower() for email in emails]
    cfg = reload_config()
    assert cfg.allowed_emails == expected


def test_telegram_credentials_loaded_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token-123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
    cfg = reload_config()
    assert cfg.telegram_bot_token == "test-token-123"
    assert cfg.telegram_chat_id == "987654321"


def test_telegram_credentials_absent_when_env_unset(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    cfg = reload_config()
    # config.yaml has empty-string defaults for both fields (server.telegram_bot_token: '')
    # so no token should be present when the env vars are unset.
    assert not cfg.telegram_bot_token
    assert not cfg.telegram_chat_id


# Regression guard: the compromised token from commit 30b8f36 must never appear as a
# default value loaded from config.yaml, regardless of env-var state.
# This token was publicly exposed on 2025-07-23 and must be treated as revoked.
# It is stored here solely as a regression sentinel — not as a usable credential.
_COMPROMISED_TOKEN = "8491288399:AAGRRuCJtctSQ2igqnW56BxQ3L_c0Jsi_nA"  # noqa: S105


def test_compromised_token_not_loaded_as_default(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    cfg = reload_config()
    assert cfg.telegram_bot_token != _COMPROMISED_TOKEN, (
        "Compromised Telegram token is still present as a default in config.yaml — "
        "remove it and ensure the field defaults to an empty string."
    )


def test_allowed_emails_env_override(monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "TEST@Example.com,Other@Example.com ,")
    cfg = reload_config()
    assert cfg.allowed_emails == ["test@example.com", "other@example.com"]
    monkeypatch.delenv("ALLOWED_EMAILS")
    reload_config()


def test_cors_origins_env_override(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://app.allotmint.io,http://192.168.1.25:5173,http://localhost:5173",
    )
    cfg = reload_config()
    assert cfg.cors_origins == [
        "https://app.allotmint.io",
        "http://192.168.1.25:5173",
        "http://localhost:5173",
    ]
    monkeypatch.delenv("CORS_ORIGINS")
    reload_config()


def test_reload_preserves_monkeypatched_allowed_emails(monkeypatch):
    reload_config()
    monkeypatch.setattr(config, "allowed_emails", ["override@example.com"], raising=False)
    cfg = reload_config()
    assert cfg.allowed_emails == ["override@example.com"]
    reload_config()


@pytest.mark.parametrize(
    "config_text",
    [
        "demo_identity: legacy-demo\nsmoke_identity: legacy-smoke\nauth:\n  demo_identity: section-demo\n  smoke_identity: section-smoke\n",
        "auth:\n  demo_identity: section-demo\n  smoke_identity: section-smoke\ndemo_identity: legacy-demo\nsmoke_identity: legacy-smoke\n",
    ],
)
def test_reload_prefers_canonical_auth_section_over_legacy_top_level(monkeypatch, tmp_path, config_text):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_text)

    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    cfg = reload_config()
    try:
        assert cfg.demo_identity == "section-demo"
        assert cfg.smoke_identity == "section-smoke"
        assert demo_identity() == "section-demo"
        assert smoke_identity() == "section-smoke"
    finally:
        monkeypatch.undo()
        reload_config()


def test_google_auth_requires_client_id(monkeypatch):
    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    with pytest.raises(ConfigValidationError):
        reload_config()
    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "false")
    reload_config()


def test_invalid_yaml_raises_config_error(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("invalid: [unclosed\n")
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)
    with pytest.raises(ConfigValidationError):
        reload_config()
    monkeypatch.undo()
    reload_config()


def test_update_config_rejects_invalid_google_auth(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("auth:\n  google_auth_enabled: false\n")

    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_AUTH_ENABLED", raising=False)

    reload_config()

    client = TestClient(create_app())

    resp = client.put("/config", json={"auth": {"google_auth_enabled": True}})
    assert resp.status_code == 400

    resp = client.put("/config", json={"google_auth_enabled": True})
    assert resp.status_code == 400

    resp = client.put("/config", json={"auth": {"google_auth_enabled": "maybe"}})
    assert resp.status_code == 400

    resp = client.put("/config", json={"auth": {"google_auth_enabled": 2}})
    assert resp.status_code == 400

    cfg = reload_config()
    assert cfg.google_auth_enabled is False


def test_update_config_merges_ui_section(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("tabs:\n  instrument: true\n")

    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    reload_config()

    client = TestClient(create_app())

    resp = client.put("/config", json={"ui": {"tabs": {"instrument": False}}})
    assert resp.status_code == 200

    data = yaml.safe_load(config_path.read_text())
    assert "tabs" not in data
    assert data["ui"]["tabs"]["instrument"] is False

    cfg = reload_config()
    assert cfg.tabs.instrument is False


def test_aws_ui_auth_loads_from_env(monkeypatch):
    monkeypatch.setenv("UI_AUTH_DOMAIN", "https://allotmint-123.auth.eu-west-1.amazoncognito.com")
    monkeypatch.setenv("UI_AUTH_CLIENT_ID", "abc123")
    cfg = reload_config()
    try:
        assert cfg.aws_ui_auth.enabled is True
        assert cfg.aws_ui_auth.domain == "https://allotmint-123.auth.eu-west-1.amazoncognito.com"
        assert cfg.aws_ui_auth.client_id == "abc123"
    finally:
        monkeypatch.delenv("UI_AUTH_DOMAIN")
        monkeypatch.delenv("UI_AUTH_CLIENT_ID")
        reload_config()


def test_aws_ui_auth_disabled_when_env_absent(monkeypatch):
    monkeypatch.delenv("UI_AUTH_DOMAIN", raising=False)
    monkeypatch.delenv("UI_AUTH_CLIENT_ID", raising=False)
    cfg = reload_config()
    assert cfg.aws_ui_auth.enabled is False
