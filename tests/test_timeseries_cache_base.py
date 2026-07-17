import importlib
import os
import sys
import threading
from datetime import datetime, timezone

import pandas as pd
import pytest

from backend.config import reload_config


def import_cache():
    """Import ``backend.timeseries.cache`` after clearing any previous copy."""
    sys.modules.pop("backend.timeseries.cache", None)
    return importlib.import_module("backend.timeseries.cache")


def patch_s3_client(monkeypatch, cache, client):
    created_clients = []

    def fake_client(service):
        assert service == "s3"
        created_clients.append(service)
        return client

    cache._s3_client.cache_clear()
    monkeypatch.setattr(cache.boto3, "client", fake_client)
    return created_clients


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

    created_clients = patch_s3_client(monkeypatch, cache, FakeS3Client())

    assert cache.has_cached_meta_timeseries("aapl", "us") is True
    assert cache.has_cached_meta_timeseries("aapl", "us") is True
    assert calls == [
        ("bucket", "timeseries/meta/AAPL_US.parquet"),
        ("bucket", "timeseries/meta/AAPL_US.parquet"),
    ]
    assert created_clients == ["s3"]


def test_has_cached_meta_timeseries_returns_false_for_missing_s3_object(monkeypatch):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()

    class FakeS3Client:
        def head_object(self, Bucket, Key):  # noqa: N803 - boto3 API parameter names
            raise cache.ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )

    created_clients = patch_s3_client(monkeypatch, cache, FakeS3Client())

    assert cache.has_cached_meta_timeseries("missing", "us") is False
    assert created_clients == ["s3"]


def test_has_cached_meta_timeseries_skips_repeat_head_object_for_confirmed_missing(monkeypatch):
    """A permanently-uncached ticker should only pay for one live HeadObject
    call within the negative-cache TTL, not one per lookup.

    Regression guard for the retry storm in issue #5093: requests touching a
    delisted/unresolvable ticker were issuing a synchronous S3 HeadObject call
    on every check, stacking up into hundreds of calls within a single
    request and exhausting the Lambda's 30s timeout.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()
    calls = []

    class FakeS3Client:
        def head_object(self, Bucket, Key):  # noqa: N803 - boto3 API parameter names
            calls.append((Bucket, Key))
            raise cache.ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )

    patch_s3_client(monkeypatch, cache, FakeS3Client())

    for _ in range(5):
        assert cache.has_cached_meta_timeseries("missing", "us") is False

    assert len(calls) == 1


def test_has_cached_meta_timeseries_rechecks_after_negative_cache_ttl_expires(monkeypatch):
    """The negative cache must expire after ``_S3_HEAD_MISS_TTL_SECONDS`` so a
    ticker whose data appears in S3 after an initial 404 (e.g. delayed data
    load) is re-checked instead of being reported missing forever.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()
    calls = []

    # Advance by a fixed 61s (not derived from the module constant) so the
    # test actually exercises the documented 60s TTL: if a future change sets
    # _S3_HEAD_MISS_TTL_SECONDS to e.g. 3600, the cache would still be valid
    # after 61s and this test would correctly fail instead of silently
    # adapting to the new value.
    assert cache._S3_HEAD_MISS_TTL_SECONDS == 60.0

    class FakeS3Client:
        def head_object(self, Bucket, Key):  # noqa: N803 - boto3 API parameter names
            calls.append((Bucket, Key))
            raise cache.ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )

    patch_s3_client(monkeypatch, cache, FakeS3Client())

    current_time = [1000.0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: current_time[0])

    assert cache.has_cached_meta_timeseries("missing", "us") is False
    assert len(calls) == 1

    # Still within the TTL: cached negative result, no new HeadObject call.
    current_time[0] += 59
    assert cache.has_cached_meta_timeseries("missing", "us") is False
    assert len(calls) == 1

    # TTL has elapsed: the cache must expire and re-check S3.
    current_time[0] += 2
    assert cache.has_cached_meta_timeseries("missing", "us") is False
    assert len(calls) == 2


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


def test_has_cached_meta_timeseries_returns_false_for_non_404_client_error(monkeypatch):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()

    class FakeS3Client:
        def head_object(self, Bucket, Key):  # noqa: N803 - boto3 API parameter names
            raise cache.ClientError(
                {"Error": {"Code": "403", "Message": "Forbidden"}},
                "HeadObject",
            )

    created_clients = patch_s3_client(monkeypatch, cache, FakeS3Client())

    assert cache.has_cached_meta_timeseries("restricted", "us") is False
    assert created_clients == ["s3"]


def test_has_cached_meta_timeseries_returns_false_when_s3_client_creation_fails(monkeypatch):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()
    created_clients = []

    def fake_client(service):
        assert service == "s3"
        created_clients.append(service)
        raise cache.BotoCoreError()

    cache._s3_client.cache_clear()
    monkeypatch.setattr(cache.boto3, "client", fake_client)

    assert cache.has_cached_meta_timeseries("any", "us") is False
    assert created_clients == ["s3"]


def test_s3_cache_object_exists_returns_false_for_invalid_path(monkeypatch):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()

    assert cache._s3_cache_object_exists("s3://") is False
    assert cache._s3_cache_object_exists("s3:///nokey") is False
    assert cache._s3_cache_object_exists("s3://bucket") is False


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

    patch_s3_client(monkeypatch, cache, FakeS3())

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


def test_load_meta_timeseries_skips_repeat_head_object_for_confirmed_missing_cache(monkeypatch):
    """``_invalidate_meta_caches_if_stale`` must not re-issue a live S3
    HeadObject call on every request for a ticker with no cache object at
    all -- see issue #5093 for the production retry-storm this caused.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()
    calls = []

    class FakeS3:
        def head_object(self, *, Bucket, Key):
            calls.append((Bucket, Key))
            raise cache.ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )

    patch_s3_client(monkeypatch, cache, FakeS3())

    loads = []

    def fake_rolling_cache(*_args, **_kwargs):
        loads.append(1)
        return _frame(1.0)

    monkeypatch.setattr(cache, "_rolling_cache", fake_rolling_cache)

    for _ in range(5):
        cache.load_meta_timeseries("MISSING", "L", 5)

    assert len(calls) == 1


def test_has_cached_meta_timeseries_thread_safe_for_confirmed_missing(monkeypatch):
    """Concurrent lookups of the same permanently-uncached ticker must still
    only pay for one live HeadObject call, and the negative cache must not
    corrupt under concurrent read/write access.

    Regression guard for issue #5104: ``_S3_HEAD_MISS_CACHE`` was a plain
    dict with no locking, so concurrent threads could race past the TTL
    check and each issue their own HeadObject call.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()
    calls = []
    calls_lock = threading.Lock()

    class FakeS3Client:
        def head_object(self, Bucket, Key):  # noqa: N803 - boto3 API parameter names
            with calls_lock:
                calls.append((Bucket, Key))
            raise cache.ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )

    patch_s3_client(monkeypatch, cache, FakeS3Client())

    results = []
    results_lock = threading.Lock()

    def worker():
        result = cache.has_cached_meta_timeseries("missing", "us")
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results == [False] * 10
    assert len(calls) == 1


def test_s3_object_mtime_returns_none_for_confirmed_missing(monkeypatch):
    """``_s3_object_mtime`` must signal confirmed-missing objects with a
    sentinel (``None``) rather than ``0.0``, so ``_invalidate_meta_caches_if_stale``
    can short-circuit instead of treating every check as a stale-cache
    transition. See issue #5107.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()

    class FakeS3:
        def head_object(self, *, Bucket, Key):
            raise cache.ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )

    patch_s3_client(monkeypatch, cache, FakeS3())

    cache_uri = "s3://bucket/timeseries/meta/MISSING_L.parquet"
    assert cache._s3_object_mtime(cache_uri) == 0.0
    assert cache._s3_object_mtime(cache_uri) is None


def test_invalidate_meta_caches_skips_update_for_confirmed_missing(monkeypatch):
    """Once a ticker is confirmed missing, repeat invalidation checks must
    not touch ``_CACHE_FILE_MTIMES`` or re-clear the LRUs -- the negative
    cache should be a true no-op fast path, not just a HeadObject skip.
    """
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()

    class FakeS3:
        def head_object(self, *, Bucket, Key):
            raise cache.ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )

    patch_s3_client(monkeypatch, cache, FakeS3())

    clears = []
    monkeypatch.setattr(cache._load_meta_timeseries_cached, "cache_clear", lambda: clears.append(1))
    monkeypatch.setattr(cache._memoized_range_cached, "cache_clear", lambda: clears.append(1))

    cache._invalidate_meta_caches_if_stale("MISSING", "L")
    cache_uri = cache.meta_timeseries_cache_path("MISSING", "L")
    assert cache._CACHE_FILE_MTIMES[cache_uri] == 0.0
    assert len(clears) == 0  # first-ever miss: prev was None, no clear triggered

    cache._invalidate_meta_caches_if_stale("MISSING", "L")
    assert cache._CACHE_FILE_MTIMES[cache_uri] == 0.0
    assert len(clears) == 0  # confirmed-missing fast path: no further work


def test_s3_range_cache_invalidates_when_last_modified_changes(monkeypatch):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", "s3://bucket/timeseries")
    cache = import_cache()

    last_modified = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)

    class FakeS3:
        def head_object(self, *, Bucket, Key):
            return {"LastModified": last_modified}

    patch_s3_client(monkeypatch, cache, FakeS3())

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
