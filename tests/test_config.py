from backend import config as config_module


def test_config_alias_settings():
    assert config_module.settings is config_module.config


def test_config_loads_fundamentals_ttl():
    cfg = config_module.load_config()
    assert cfg.fundamentals_cache_ttl_seconds == 86400


def test_tabs_loaded():
    cfg = config_module.load_config()
    assert cfg.tabs.instrument is True
    assert cfg.tabs.support is True
    assert cfg.tabs.timeseries is True
    assert cfg.tabs.reports is True
    assert cfg.tabs.performance is False


def test_theme_loaded():
    cfg = config_module.load_config()
    assert cfg.theme == "system"
