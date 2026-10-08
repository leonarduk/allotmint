import sys

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import (
    ConfigValidationError,
    _flatten_dict,
    _project_config_path,
    build_config,
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


def test_nav_max_age_days_is_read_from_market_data():
    data: dict = {}
    _flatten_dict({"market_data": {"nav_max_age_days": 14}}, data)

    assert build_config(data, check_google_auth=False).nav_max_age_days == 14
    assert build_config({}, check_google_auth=False).nav_max_age_days is None


def test_nav_refresh_settings_are_read_from_market_data():
    data: dict = {}
    _flatten_dict(
        {
            "market_data": {
                "nav_refresh_enabled": True,
                "nav_refresh_time": "7:05",
                "nav_refresh_request_interval_seconds": 5,
                "nav_refresh_cache_ttl_seconds": 60,
            }
        },
        data,
    )

    cfg = build_config(data, check_google_auth=False)
    assert cfg.nav_refresh_enabled is True
    assert cfg.nav_refresh_time == "07:05"
    assert cfg.nav_refresh_request_interval_seconds == 5.0
    assert cfg.nav_refresh_cache_ttl_seconds == 60


def test_nav_refresh_defaults_off_after_close():
    cfg = build_config({}, check_google_auth=False)
    assert cfg.nav_refresh_enabled is False
    assert cfg.nav_refresh_time == "18:30"


@pytest.mark.parametrize("raw", ["25:00", "18:3", "evening", 1110])
def test_nav_refresh_time_rejects_non_hh_mm(raw):
    # 1110 is what YAML makes of an unquoted 18:30 (base-60).
    with pytest.raises(ConfigValidationError, match="nav_refresh_time"):
        build_config({"nav_refresh_time": raw}, check_google_auth=False)


@pytest.mark.parametrize("key", ["nav_refresh_request_interval_seconds", "nav_refresh_cache_ttl_seconds"])
@pytest.mark.parametrize("raw", ["abc", -1, True])
def test_nav_refresh_numbers_must_be_non_negative(key, raw):
    with pytest.raises(ConfigValidationError, match=key):
        build_config({key: raw}, check_google_auth=False)


def test_config_example_nav_refresh_time_parses_as_string():
    from pathlib import Path

    example = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.example.yaml").read_text(encoding="utf-8"))
    assert example["market_data"]["nav_refresh_time"] == "18:30"


@pytest.mark.parametrize("raw", ["[object Object]", ["pytest"], 3])
def test_error_summary_ignores_non_mapping_values(raw, caplog):
    """A stringified JS object must not leak out of /config (#7788)."""

    with caplog.at_level("WARNING", logger="backend.config"):
        cfg = build_config({"error_summary": raw}, check_google_auth=False)

    assert cfg.error_summary is None
    assert "Ignoring error_summary" in caplog.text


def test_error_summary_keeps_a_mapping():
    value = {"default_command": ["pytest"]}

    assert build_config({"error_summary": value}, check_google_auth=False).error_summary == value


def test_example_config_has_no_stringified_objects():
    from pathlib import Path

    example = Path(__file__).resolve().parents[1] / "config.example.yaml"
    assert "[object Object]" not in example.read_text(encoding="utf-8")


def test_uvicorn_port_default():
    """Pin the local dev backend port so a future config edit can't drift silently.

    6468 spells MINT on a phone keypad (#7811); regressing to the old 8000
    default would go unnoticed without an explicit assertion here.
    """
    cfg = reload_config()
    assert cfg.uvicorn_port == 6468


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
        assert cfg.enable_family_mvp is False
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
        assert cfg.enable_family_mvp is False
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


def test_audit_dir_defaults_under_data_root(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("data_root: data\n")
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    cfg = reload_config()
    try:
        assert cfg.audit_dir == cfg.data_root / "audit"
    finally:
        monkeypatch.undo()
        reload_config()


def test_audit_dir_rejects_path_outside_data_root(monkeypatch, tmp_path):
    """A ``../``-escaping or absolute ``audit_dir`` must be rejected at load,
    not silently resolved outside data_root (#6739)."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("data_root: data\naudit_dir: ../../etc\n")
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    with pytest.raises(ConfigValidationError):
        reload_config()
    monkeypatch.undo()
    reload_config()


def test_audit_dir_accepts_path_inside_data_root(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("data_root: data\naudit_dir: custom-audit\n")
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    cfg = reload_config()
    try:
        assert cfg.audit_dir == cfg.data_root / "custom-audit"
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


def test_skip_snapshot_warm_env_override(monkeypatch):
    """SKIP_SNAPSHOT_WARM lets Lambda disable blocking warmup without a code
    change (issue #4930's fast rollback lever)."""
    monkeypatch.delenv("SKIP_SNAPSHOT_WARM", raising=False)
    default_value = reload_config().skip_snapshot_warm

    monkeypatch.setenv("SKIP_SNAPSHOT_WARM", "true")
    cfg = reload_config()
    assert cfg.skip_snapshot_warm is True

    monkeypatch.setenv("SKIP_SNAPSHOT_WARM", "false")
    cfg = reload_config()
    assert cfg.skip_snapshot_warm is False

    monkeypatch.delenv("SKIP_SNAPSHOT_WARM")
    assert reload_config().skip_snapshot_warm == default_value


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


def test_demo_link_defaults_when_keys_absent(monkeypatch, tmp_path):
    """A missing `demo_link_*` block must never mean the demo link is on."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("auth:\n  demo_identity: steve\n")
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    cfg = reload_config()
    try:
        assert cfg.demo_link_enabled is False
        assert cfg.demo_link_owner is None
        assert cfg.demo_link_ttl_hours == 72
    finally:
        monkeypatch.undo()
        reload_config()


def test_demo_link_loads_from_auth_section(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "auth:\n" "  demo_link_enabled: true\n" "  demo_link_owner: demo\n" "  demo_link_ttl_hours: 24\n",
    )
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    cfg = reload_config()
    try:
        assert cfg.demo_link_enabled is True
        assert cfg.demo_link_owner == "demo"
        assert cfg.demo_link_ttl_hours == 24
    finally:
        monkeypatch.undo()
        reload_config()


def test_demo_link_owner_blank_string_falls_back_to_none(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("auth:\n  demo_link_owner: '   '\n")
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    cfg = reload_config()
    try:
        assert cfg.demo_link_owner is None
    finally:
        monkeypatch.undo()
        reload_config()


def test_demo_link_enabled_null_falls_back_to_false(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("auth:\n  demo_link_enabled: null\n")
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    cfg = reload_config()
    try:
        assert cfg.demo_link_enabled is False
    finally:
        monkeypatch.undo()
        reload_config()


def test_demo_link_enabled_rejects_non_boolean(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("auth:\n  demo_link_enabled: 'yes'\n")
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    try:
        with pytest.raises(ConfigValidationError):
            reload_config()
    finally:
        monkeypatch.undo()
        reload_config()


def test_demo_link_does_not_affect_demo_identity(monkeypatch, tmp_path):
    """`demo_link_owner` must stay distinct from `demo_identity` -- the
    latter keeps its display/local-mode meaning (#7404)."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "auth:\n" "  demo_identity: steve\n" "  demo_link_enabled: true\n" "  demo_link_owner: demo\n",
    )
    monkeypatch.setattr(sys.modules["backend.config"], "_project_config_path", lambda: config_path)
    monkeypatch.setattr(routes_config, "_project_config_path", lambda: config_path)

    cfg = reload_config()
    try:
        assert cfg.demo_identity == "steve"
        assert demo_identity() == "steve"
        assert cfg.demo_link_owner == "demo"
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


def test_allowed_emails_env_override(monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "TEST@Example.com,Other@Example.com ,")
    cfg = reload_config()
    assert cfg.allowed_emails == ["test@example.com", "other@example.com"]
    monkeypatch.delenv("ALLOWED_EMAILS")
    reload_config()


def test_cors_origins_env_override(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://app.allotmint.io,http://192.168.1.25:2568,http://localhost:2568",
    )
    cfg = reload_config()
    assert cfg.cors_origins == [
        "https://app.allotmint.io",
        "http://192.168.1.25:2568",
        "http://localhost:2568",
    ]
    monkeypatch.delenv("CORS_ORIGINS")
    reload_config()


def test_cors_origin_regex_env_override(monkeypatch):
    monkeypatch.setenv("CORS_ORIGIN_REGEX", r"^http://localhost:5\d{3}$")
    cfg = reload_config()
    assert cfg.cors_origin_regex == r"^http://localhost:5\d{3}$"
    monkeypatch.delenv("CORS_ORIGIN_REGEX")
    reload_config()


def test_cors_origin_regex_env_empty_string_disables(monkeypatch):
    """An empty env value switches the regex off rather than matching nothing.

    `CORS_ORIGIN_REGEX=""` is how an operator disables an inherited setting; a
    literal empty pattern would match every origin prefix instead.
    """
    monkeypatch.setenv("CORS_ORIGIN_REGEX", "")
    cfg = reload_config()
    assert cfg.cors_origin_regex is None
    monkeypatch.delenv("CORS_ORIGIN_REGEX")
    reload_config()


def test_cors_origin_regex_defaults_to_none(monkeypatch):
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
    cfg = reload_config()
    assert cfg.cors_origin_regex is None


def test_cors_origin_regex_invalid_pattern_rejected(monkeypatch):
    """A bad pattern fails at config load, not on the first cross-origin call."""
    monkeypatch.setenv("CORS_ORIGIN_REGEX", "^http://localhost:(5\d{3}$")
    with pytest.raises(ConfigValidationError, match="Invalid CORS origin regex"):
        reload_config()
    monkeypatch.delenv("CORS_ORIGIN_REGEX")
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
        (
            "demo_identity: legacy-demo\n"
            "smoke_identity: legacy-smoke\n"
            "auth:\n"
            "  demo_identity: section-demo\n"
            "  smoke_identity: section-smoke\n"
        ),
        (
            "auth:\n"
            "  demo_identity: section-demo\n"
            "  smoke_identity: section-smoke\n"
            "demo_identity: legacy-demo\n"
            "smoke_identity: legacy-smoke\n"
        ),
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


def test_aws_ui_auth_disabled_when_only_domain_set(monkeypatch):
    """
    #4630

    Set UI_AUTH_DOMAIN to a valid domain, leave UI_AUTH_CLIENT_ID unset/empty.

    Assert that enabled is False and that the serialized /config response
    omits awsUiAuth (or includes it with enabled: false depending
    on the serialization logic — verify against routes/config.py line 71).
    """
    monkeypatch.setenv("UI_AUTH_DOMAIN", "https://allotmint-123.auth.eu-west-1.amazoncognito.com")
    monkeypatch.setenv("UI_AUTH_CLIENT_ID", "")
    cfg = reload_config()
    try:
        assert cfg.aws_ui_auth.enabled is False
        assert cfg.aws_ui_auth.domain == "https://allotmint-123.auth.eu-west-1.amazoncognito.com"
        assert cfg.aws_ui_auth.client_id is None
        assert "awsUiAuth" not in routes_config.serialise_config(cfg)
    finally:
        monkeypatch.delenv("UI_AUTH_DOMAIN")
        monkeypatch.delenv("UI_AUTH_CLIENT_ID")
        reload_config()


def test_aws_ui_auth_disabled_when_only_client_id_set(monkeypatch):
    """
    #4630

    Set UI_AUTH_CLIENT_ID to a valid client ID, leave UI_AUTH_DOMAIN unset/empty.

    Assert that enabled is False and that the serialized /config response
    omits awsUiAuth (or includes it with enabled: false depending
    on the serialization logic — verify against routes/config.py line 71).

    """
    monkeypatch.setenv("UI_AUTH_DOMAIN", "")
    monkeypatch.setenv("UI_AUTH_CLIENT_ID", "abc123")
    cfg = reload_config()
    try:
        assert cfg.aws_ui_auth.enabled is False
        assert cfg.aws_ui_auth.domain is None
        assert cfg.aws_ui_auth.client_id == "abc123"
        assert "awsUiAuth" not in routes_config.serialise_config(cfg)
    finally:
        monkeypatch.delenv("UI_AUTH_DOMAIN")
        monkeypatch.delenv("UI_AUTH_CLIENT_ID")
        reload_config()


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
