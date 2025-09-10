import pytest

import backend.timeseries.cache as cache_module
import backend.config as config_module


def reload_cache():
    import importlib
    return importlib.reload(cache_module)


def test_missing_cache_base_raises(monkeypatch):
    import importlib
    importlib.reload(config_module)
    monkeypatch.delenv("TIMESERIES_CACHE_BASE", raising=False)
    monkeypatch.setattr(config_module.config, "timeseries_cache_base", None)
    cache = reload_cache()
    with pytest.raises(ValueError, match="TIMESERIES_CACHE_BASE"):
        cache._cache_path("foo")


def test_cache_base_from_env(monkeypatch, tmp_path):
    import importlib
    importlib.reload(config_module)
    monkeypatch.setattr(config_module.config, "timeseries_cache_base", None)
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = reload_cache()
    assert cache._cache_path("bar") == str(tmp_path / "bar")


def test_cache_base_from_config(monkeypatch, tmp_path):
    import importlib
    importlib.reload(config_module)
    monkeypatch.delenv("TIMESERIES_CACHE_BASE", raising=False)
    monkeypatch.setattr(config_module.config, "timeseries_cache_base", str(tmp_path))
    cache = reload_cache()
    assert cache._cache_path("baz") == str(tmp_path / "baz")

