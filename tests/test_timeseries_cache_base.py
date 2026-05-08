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


def test_has_cached_meta_timeseries_returns_true_for_existing_s3_object(monkeypatch):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()
    calls = []

    class FakeS3Client:
        def head_object(self, Bucket, Key):  # noqa: N803 - boto3 API parameter names
            calls.append((Bucket, Key))
            return {"ContentLength": 10}

    monkeypatch.setattr(cache.boto3, "client", lambda service: FakeS3Client())

    assert cache.has_cached_meta_timeseries("aapl", "us") is True
    assert calls == [("bucket", "timeseries/meta/AAPL_US.parquet")]


def test_has_cached_meta_timeseries_returns_false_for_missing_s3_object(monkeypatch):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()

    class FakeS3Client:
        def head_object(self, Bucket, Key):  # noqa: N803 - boto3 API parameter names
            raise cache.ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )

    monkeypatch.setattr(cache.boto3, "client", lambda service: FakeS3Client())

    assert cache.has_cached_meta_timeseries("missing", "l") is False


def test_has_cached_meta_timeseries_keeps_local_path_behaviour(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()

    assert cache.has_cached_meta_timeseries("empty", "l") is False

    path = tmp_path / "meta" / "EMPTY_L.parquet"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"")
    assert cache.has_cached_meta_timeseries("empty", "l") is False

    path.write_bytes(b"cached")
    assert cache.has_cached_meta_timeseries("empty", "l") is True
