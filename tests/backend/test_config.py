"""Tests for backend/config.py, focusing on default value consistency."""

from __future__ import annotations

import dataclasses

import pytest

from backend.config import Config, build_config, load_config


class TestRateLimitDefault:
    """Ensure rate_limit_per_minute has a single, consistent default."""

    def test_dataclass_default_is_6000(self) -> None:
        """Directly-constructed Config uses the dataclass field default."""
        cfg = Config()
        assert cfg.rate_limit_per_minute == 6000

    def test_load_config_without_key_uses_dataclass_default(self) -> None:
        """A config omitting the key resolves to the same value as Config()."""
        # Build from empty data (no rate_limit_per_minute key)
        cfg = build_config({})
        assert cfg.rate_limit_per_minute == 6000

    def test_load_config_with_key_preserves_explicit_value(self) -> None:
        """An explicit value in config data still wins."""
        cfg = build_config({"rate_limit_per_minute": 120})
        assert cfg.rate_limit_per_minute == 120

    def test_load_config_with_zero_is_preserved(self) -> None:
        """Zero is a valid explicit value and must not be treated as missing."""
        cfg = build_config({"rate_limit_per_minute": 0})
        assert cfg.rate_limit_per_minute == 0

    def test_all_construction_paths_agree(self) -> None:
        """Config(), build_config({}), and load_config() all agree when key is absent."""
        direct = Config()
        built = build_config({})
        loaded = load_config()

        # load_config() reads the real config.yaml which sets 6000 explicitly,
        # so it should match the dataclass default too.
        assert direct.rate_limit_per_minute == 6000
        assert built.rate_limit_per_minute == 6000
        assert loaded.rate_limit_per_minute == 6000
        assert direct.rate_limit_per_minute == built.rate_limit_per_minute == loaded.rate_limit_per_minute


class TestOtherDefaultsConsistency:
    """Spot-check that other defaults don't drift between dataclass and loader."""

    @pytest.mark.parametrize(
        ("field_name", "expected_default"),
        [
            ("signup_rate_limit", "5/minute"),
            ("demo_link_mint_rate_limit", "5/minute"),
            ("news_requests_per_day", 25),
            ("yahoo_news_requests_per_day", 500),
            ("google_news_requests_per_day", 500),
            ("default_sector_region", "US"),
            ("demo_link_ttl_hours", 72),
            ("demo_link_enabled", False),
            ("enforce_owner_access", False),
            ("enable_family_mvp", False),
            ("enable_compliance_workflows", False),
            ("enable_advanced_analytics", False),
            ("enable_reporting_extended", False),
            ("enable_data_quality_admin", True),
        ],
    )
    def test_field_defaults_match(self, field_name: str, expected_default: object) -> None:
        """Dataclass default and build_config({}) default agree for each field."""
        direct = Config()
        built = build_config({})
        assert getattr(direct, field_name) == expected_default
        assert getattr(built, field_name) == expected_default
        assert getattr(direct, field_name) == getattr(built, field_name)


# Environment variables build_config() reads; cleared so the comparison below
# sees only the two sets of defaults.
_BUILD_CONFIG_ENV = (
    "ALLOWED_EMAILS",
    "ALPHA_VANTAGE_KEY",
    "APP_ENV",
    "BEDROCK_MODEL_ID",
    "CHAT_BASE_URL",
    "CHAT_MODEL",
    "CHAT_PROVIDER",
    "CORS_ORIGINS",
    "CORS_ORIGIN_REGEX",
    "DATA_ROOT",
    "DISABLE_AUTH",
    "ENFORCE_OWNER_ACCESS",
    "ENVIRONMENT",
    "GOOGLE_AUTH_ENABLED",
    "GOOGLE_CLIENT_ID",
    "LOCAL_LOGIN_EMAIL",
    "LOG_FORMAT",
    "MCP_SERVER_URL",
    "SKIP_SNAPSHOT_WARM",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TIMESERIES_CACHE_BASE",
    "UI_AUTH_CLIENT_ID",
    "UI_AUTH_DOMAIN",
)

# Resolved against the config file's directory by build_config(), so they
# have no meaningful dataclass default to compare with.
_DERIVED_PATH_FIELDS = {"repo_root", "data_root", "audit_dir"}


def test_every_dataclass_default_matches_build_config_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config() and build_config({}) agree on every field, not just a spot-checked few (#7672)."""
    for name in _BUILD_CONFIG_ENV:
        monkeypatch.delenv(name, raising=False)
    direct = Config()
    built = build_config({})
    drift = {
        field.name: (getattr(direct, field.name), getattr(built, field.name))
        for field in dataclasses.fields(Config)
        if field.name not in _DERIVED_PATH_FIELDS and getattr(direct, field.name) != getattr(built, field.name)
    }
    assert drift == {}


class TestChatProviderEnv:
    """CHAT_PROVIDER / CHAT_MODEL / CHAT_BASE_URL env overrides (#7873)."""

    def test_unset_leaves_provider_model_and_base_url_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("CHAT_PROVIDER", "CHAT_MODEL", "CHAT_BASE_URL"):
            monkeypatch.delenv(name, raising=False)
        cfg = build_config({})
        assert (cfg.chat_provider, cfg.chat_model, cfg.chat_base_url) == (None, None, None)

    def test_env_values_are_read_and_provider_is_lowercased(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CHAT_PROVIDER", " Ollama ")
        monkeypatch.setenv("CHAT_MODEL", "qwen3.5:9b")
        monkeypatch.setenv("CHAT_BASE_URL", "http://gpu-box:11434/v1")
        cfg = build_config({})
        assert (cfg.chat_provider, cfg.chat_model, cfg.chat_base_url) == (
            "ollama",
            "qwen3.5:9b",
            "http://gpu-box:11434/v1",
        )

    def test_unknown_provider_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CHAT_PROVIDER", "openai")
        with pytest.raises(ValueError, match="Unexpected CHAT_PROVIDER"):
            build_config({})


def test_per_provider_news_quotas_are_read_from_config() -> None:
    cfg = build_config({"yahoo_news_requests_per_day": 7, "google_news_requests_per_day": 9})
    assert (cfg.yahoo_news_requests_per_day, cfg.google_news_requests_per_day) == (7, 9)
