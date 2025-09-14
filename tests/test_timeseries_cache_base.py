import importlib
import sys

import pytest

from backend.config import reload_config


def import_cache():
    """Import ``backend.timeseries.cache`` after clearing any previous copy."""
    sys.modules.pop("backend.timeseries.cache", None)
    return importlib.import_module("backend.timeseries.cache")


def test_missing_cache_base_raises(monkeypatch):
    reload_config()
    monkeypatch.delenv("TIMESERIES_CACHE_BASE", raising=False)
    cfg_module = sys.modules["backend.config"]
    monkeypatch.setattr(cfg_module.config, "timeseries_cache_base", None)
    sys.modules.pop("backend.timeseries.cache", None)
    with pytest.raises(ValueError, match="TIMESERIES_CACHE_BASE"):
        import_cache()


def test_cache_base_from_env(monkeypatch, tmp_path):
    reload_config()
    cfg_module = sys.modules["backend.config"]
    monkeypatch.setattr(cfg_module.config, "timeseries_cache_base", None)
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    assert cache._cache_path("bar") == str(tmp_path / "bar")


def test_cache_base_from_config(monkeypatch, tmp_path):
    reload_config()
    monkeypatch.delenv("TIMESERIES_CACHE_BASE", raising=False)
    cfg_module = sys.modules["backend.config"]
    monkeypatch.setattr(cfg_module.config, "timeseries_cache_base", str(tmp_path))
    cache = import_cache()
    assert cache._cache_path("baz") == str(tmp_path / "baz")

