from backend import config as config_module


def test_config_alias_settings():
    assert config_module.settings is config_module.config
