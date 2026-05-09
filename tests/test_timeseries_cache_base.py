import importlib
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
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


def _frame(close: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-05-08")],
            "Open": [close],
            "High": [close],
            "Low": [close],
            "Close": [close],
            "Volume": [100],
            "Ticker": ["ABC"],
            "Source": ["TEST"],
        }
    )


def test_s3_meta_cache_invalidates_when_last_modified_changes(monkeypatch):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()

    last_modified = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)

    class FakeS3:
        def head_object(self, *, Bucket, Key):
            assert Bucket == "bucket"
            assert Key == "timeseries/meta/ABC_L.parquet"
            return {"LastModified": last_modified}

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda _service: FakeS3()))

    loads = []

    def fake_rolling_cache(*_args, **_kwargs):
        loads.append(last_modified)
        return _frame(float(len(loads)))

    monkeypatch.setattr(cache, "_rolling_cache", fake_rolling_cache)

    first = cache.load_meta_timeseries("ABC", "L", 5)
    second = cache.load_meta_timeseries("ABC", "L", 5)

    last_modified = datetime(2026, 5, 8, 12, 5, tzinfo=timezone.utc)
    third = cache.load_meta_timeseries("ABC", "L", 5)

    assert first["Close"].iloc[0] == 1.0
    assert second["Close"].iloc[0] == 1.0
    assert third["Close"].iloc[0] == 2.0
    assert len(loads) == 2


def test_local_meta_cache_still_invalidates_when_file_mtime_changes(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    cache_file = tmp_path / "meta" / "ABC_L.parquet"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text("old", encoding="utf-8")

    loads = []

    def fake_rolling_cache(*_args, **_kwargs):
        loads.append(cache_file.stat().st_mtime)
        return _frame(float(len(loads)))

    monkeypatch.setattr(cache, "_rolling_cache", fake_rolling_cache)

    first = cache.load_meta_timeseries("ABC", "L", 5)
    second = cache.load_meta_timeseries("ABC", "L", 5)

    changed_mtime = cache_file.stat().st_mtime + 10
    os.utime(cache_file, (changed_mtime, changed_mtime))
    third = cache.load_meta_timeseries("ABC", "L", 5)

    assert first["Close"].iloc[0] == 1.0
    assert second["Close"].iloc[0] == 1.0
    assert third["Close"].iloc[0] == 2.0
    assert len(loads) == 2


def test_s3_range_cache_invalidates_when_last_modified_changes(monkeypatch):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()

    last_modified = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)

    class FakeS3:
        def head_object(self, *, Bucket, Key):
            return {"LastModified": last_modified}

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda _service: FakeS3()))

    loads = []

    def fake_rolling_cache(*_args, **_kwargs):
        loads.append(last_modified)
        return _frame(float(len(loads)))

    monkeypatch.setattr(cache, "_rolling_cache", fake_rolling_cache)

    target = pd.Timestamp("2026-05-08").date()
    first = cache.load_meta_timeseries_range("ABC", "L", target, target)
    second = cache.load_meta_timeseries_range("ABC", "L", target, target)

    last_modified = datetime(2026, 5, 8, 12, 5, tzinfo=timezone.utc)
    third = cache.load_meta_timeseries_range("ABC", "L", target, target)

    assert first["Close"].iloc[0] == 1.0
    assert second["Close"].iloc[0] == 1.0
    assert third["Close"].iloc[0] == 2.0
    assert len(loads) == 2
