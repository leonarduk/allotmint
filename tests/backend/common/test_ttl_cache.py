"""Tests for TTLCache, including single-flight coalescing of concurrent misses (#10360)."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.common.ttl_cache import TTLCache

_WAIT = 5.0


def test_returns_cached_copy_within_ttl():
    cache: TTLCache[dict] = TTLCache(60.0)
    calls = []

    def build():
        calls.append(1)
        return {"items": [1]}

    first = cache.get_or_build(("k",), build)
    first["items"].append(2)
    second = cache.get_or_build(("k",), build)

    assert calls == [1]
    assert second == {"items": [1]}


def test_rebuilds_after_ttl_expires():
    cache: TTLCache[int] = TTLCache(0.0)
    values = iter([1, 2])

    assert cache.get_or_build(("k",), lambda: next(values)) == 1
    assert cache.get_or_build(("k",), lambda: next(values)) == 2


def test_concurrent_misses_on_same_key_build_once():
    cache: TTLCache[dict] = TTLCache(60.0)
    release = threading.Event()
    calls = []
    callers = 10

    def build():
        calls.append(threading.get_ident())
        assert release.wait(_WAIT)
        return {"value": 42}

    with ThreadPoolExecutor(max_workers=callers) as pool:
        futures = [pool.submit(cache.get_or_build, ("k",), build) for _ in range(callers)]
        # Give every caller time to reach the cache before the build finishes.
        time.sleep(0.2)
        release.set()
        results = [f.result(timeout=_WAIT) for f in futures]

    assert len(calls) == 1
    assert all(r == {"value": 42} for r in results)
    # Each caller gets its own copy, so one caller's mutation is not shared.
    assert len({id(r) for r in results}) == callers


def test_build_error_reaches_every_waiter_and_is_not_cached():
    cache: TTLCache[int] = TTLCache(60.0)
    release = threading.Event()
    calls = []

    def failing_build():
        calls.append(1)
        assert release.wait(_WAIT)
        raise RuntimeError("boom")

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(cache.get_or_build, ("k",), failing_build) for _ in range(3)]
        time.sleep(0.2)
        release.set()
        for future in futures:
            with pytest.raises(RuntimeError, match="boom"):
                future.result(timeout=_WAIT)

    assert len(calls) == 1
    assert cache.get_or_build(("k",), lambda: 7) == 7


def test_slow_build_does_not_block_other_keys():
    cache: TTLCache[str] = TTLCache(60.0)
    release = threading.Event()

    def slow_build():
        assert release.wait(_WAIT)
        return "slow"

    with ThreadPoolExecutor(max_workers=1) as pool:
        slow = pool.submit(cache.get_or_build, ("a",), slow_build)
        time.sleep(0.1)
        started = time.monotonic()
        assert cache.get_or_build(("b",), lambda: "fast") == "fast"
        assert time.monotonic() - started < 1.0
        release.set()
        assert slow.result(timeout=_WAIT) == "slow"


def test_reentrant_build_for_same_key_does_not_deadlock():
    cache: TTLCache[int] = TTLCache(60.0)

    def outer():
        return cache.get_or_build(("k",), lambda: 1) + 1

    assert cache.get_or_build(("k",), outer) == 2


def test_clear_during_build_does_not_cache_stale_result():
    cache: TTLCache[str] = TTLCache(60.0)
    release = threading.Event()

    def stale_build():
        assert release.wait(_WAIT)
        return "stale"

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(cache.get_or_build, ("k",), stale_build)
        time.sleep(0.1)
        cache.clear()
        release.set()
        assert future.result(timeout=_WAIT) == "stale"

    assert cache.get_or_build(("k",), lambda: "fresh") == "fresh"
    assert len(cache) == 1
