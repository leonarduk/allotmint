from backend.config import config, settings


def test_config_alias_settings():
    assert settings is config
