from backend import config as config_module


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
    assert cfg.tabs.owner is True
    assert cfg.tabs.dataadmin is True
    assert cfg.tabs.scenario is True


def test_theme_loaded():
    cfg = config_module.load_config()
    assert cfg.theme == "system"


def test_stooq_timeout_loaded():
    cfg = config_module.load_config()
    assert cfg.stooq_timeout == 10


def test_auth_flags(monkeypatch):
    cfg = config_module.load_config()
    assert cfg.google_auth_enabled is False
    assert cfg.disable_auth is True

    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.setenv("DISABLE_AUTH", "false")
    config_module.load_config.cache_clear()
    cfg = config_module.load_config()
    assert cfg.google_auth_enabled is True
    assert cfg.disable_auth is False
    monkeypatch.delenv("GOOGLE_AUTH_ENABLED")
    monkeypatch.delenv("DISABLE_AUTH")
    config_module.load_config.cache_clear()
    config_module.config = config_module.load_config()
