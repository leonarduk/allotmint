"""Tests for backend/config.py, focusing on default value consistency."""

from __future__ import annotations

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
            ("default_sector_region", "US"),
            ("demo_link_ttl_hours", 72),
            ("demo_link_enabled", False),
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
