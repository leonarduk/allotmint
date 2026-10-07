"""Tests for TTLCache, including single-flight coalescing of concurrent misses (#10360).

The concurrency tests are sequenced with ``threading.Event`` gates and a
waiter counter (no sleeps): ``_WaiterTracker`` instruments ``_InFlight`` so a
test can block until N callers have committed to waiting on a build before it
lets that build finish.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.common import ttl_cache as ttl_cache_module
from backend.common.ttl_cache import TTLCache

_WAIT = 5.0


class _WaiterTracker:
    """Counts callers that have started waiting on any in-flight build."""

    def __init__(self) -> None:
        self.cond = threading.Condition()
        self.waiting = 0

    def wait_for(self, count: int) -> None:
        with self.cond:
            assert self.cond.wait_for(
                lambda: self.waiting >= count, timeout=_WAIT
            ), f"only {self.waiting} of {count} callers reached the in-flight build"


@pytest.fixture
def waiters(monkeypatch: pytest.MonkeyPatch) -> _WaiterTracker:
    tracker = _WaiterTracker()

    class _CountingEvent(threading.Event):
        def wait(self, timeout=None):  # type: ignore[override]
            with tracker.cond:
                tracker.waiting += 1
                tracker.cond.notify_all()
            return super().wait(timeout)

    def _init(self) -> None:
        self.done = _CountingEvent()
        self.value = None
        self.error = None

    monkeypatch.setattr(ttl_cache_module._InFlight, "__init__", _init)
    return tracker


def _gated_build(value, started: threading.Event, release: threading.Event, calls: list):
    def build():
        calls.append(value)
        started.set()
        assert release.wait(_WAIT)
        return {"value": value}

    return build


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


def test_concurrent_misses_on_same_key_build_once(waiters):
    cache: TTLCache[dict] = TTLCache(60.0)
    started, release = threading.Event(), threading.Event()
    calls: list = []
    callers = 10
    build = _gated_build("leader", started, release, calls)

    with ThreadPoolExecutor(max_workers=callers) as pool:
        leader = pool.submit(cache.get_or_build, ("k",), build)
        assert started.wait(_WAIT)
        followers = [pool.submit(cache.get_or_build, ("k",), build) for _ in range(callers - 1)]
        waiters.wait_for(callers - 1)
        release.set()
        results = [leader.result(timeout=_WAIT)] + [f.result(timeout=_WAIT) for f in followers]

    assert calls == ["leader"]
    assert all(r == {"value": "leader"} for r in results)
    # Every caller, leader included, gets its own copy: mutating one result
    # does not change another's or the cached value.
    assert len({id(r) for r in results}) == callers
    results[0]["value"] = "mutated by leader"
    results[1]["value"] = "mutated by waiter"
    assert results[2] == {"value": "leader"}
    assert cache.get_or_build(("k",), lambda: pytest.fail("should be cached")) == {"value": "leader"}


def test_build_error_reaches_every_waiter_and_next_call_retries(waiters):
    cache: TTLCache[int] = TTLCache(60.0)
    started, release = threading.Event(), threading.Event()
    calls = []

    def failing_build():
        calls.append(1)
        started.set()
        assert release.wait(_WAIT)
        raise RuntimeError("boom")

    with ThreadPoolExecutor(max_workers=3) as pool:
        leader = pool.submit(cache.get_or_build, ("k",), failing_build)
        assert started.wait(_WAIT)
        followers = [pool.submit(cache.get_or_build, ("k",), failing_build) for _ in range(2)]
        waiters.wait_for(2)
        release.set()
        for future in [leader, *followers]:
            with pytest.raises(RuntimeError, match="boom"):
                future.result(timeout=_WAIT)

    assert len(calls) == 1
    assert len(cache) == 0
    assert cache.get_or_build(("k",), lambda: 7) == 7
    assert cache.get_or_build(("k",), lambda: pytest.fail("should be cached")) == 7


def test_slow_build_does_not_block_other_keys():
    cache: TTLCache[str] = TTLCache(60.0)
    started, release = threading.Event(), threading.Event()

    def slow_build():
        started.set()
        assert release.wait(_WAIT)
        return "slow"

    with ThreadPoolExecutor(max_workers=1) as pool:
        slow = pool.submit(cache.get_or_build, ("a",), slow_build)
        assert started.wait(_WAIT)
        # Key "a" is still building (release is unset), so if this returned
        # at all, it did not wait for "a".
        assert cache.get_or_build(("b",), lambda: "fast") == "fast"
        assert not slow.done()
        release.set()
        assert slow.result(timeout=_WAIT) == "slow"


def test_reentrant_build_for_same_key_does_not_deadlock_or_leak(waiters):
    """A build that re-enters its own key builds directly; only the outer value is published."""

    cache: TTLCache[int] = TTLCache(60.0)
    started, waiter_ready = threading.Event(), threading.Event()

    def inner():
        return 1

    def outer():
        started.set()
        assert waiter_ready.wait(_WAIT)
        return cache.get_or_build(("k",), inner) + 100

    with ThreadPoolExecutor(max_workers=2) as pool:
        leader = pool.submit(cache.get_or_build, ("k",), outer)
        assert started.wait(_WAIT)
        # A *different* thread asking for the same key must wait for the
        # outer build, not take the re-entrancy escape.
        follower = pool.submit(cache.get_or_build, ("k",), lambda: pytest.fail("must wait, not build"))
        waiters.wait_for(1)
        waiter_ready.set()
        assert leader.result(timeout=_WAIT) == 101
        assert follower.result(timeout=_WAIT) == 101

    # The nested value (1) was neither published nor cached.
    assert cache.get_or_build(("k",), lambda: pytest.fail("should be cached")) == 101


def test_reentrancy_tracking_is_released_after_build():
    """Once a build finishes, the same thread is a normal caller again."""

    cache: TTLCache[int] = TTLCache(0.0)  # never fresh, so every call builds
    assert cache.get_or_build(("k",), lambda: cache.get_or_build(("k",), lambda: 1) + 1) == 2
    assert cache._keys_building_on_this_thread() == {}
    with pytest.raises(RuntimeError):
        cache.get_or_build(("k",), lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert cache._keys_building_on_this_thread() == {}


def test_clear_during_build_does_not_cache_stale_result():
    cache: TTLCache[dict] = TTLCache(60.0)
    started, release = threading.Event(), threading.Event()
    build = _gated_build("stale", started, release, [])

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(cache.get_or_build, ("k",), build)
        assert started.wait(_WAIT)
        cache.clear()
        release.set()
        assert future.result(timeout=_WAIT) == {"value": "stale"}

    assert len(cache) == 0
    assert cache.get_or_build(("k",), lambda: {"value": "fresh"}) == {"value": "fresh"}
    assert len(cache) == 1


def test_clear_mid_build_keeps_waiters_and_coalesces_post_clear_callers(waiters):
    """clear() mid-build: pre-clear waiters stay on the old build; post-clear callers share one new build.

    Post-clear callers must not join the pre-clear build: clear() is how
    writers (e.g. ``invalidate_group_portfolios`` after an account write)
    say the data changed, so the old build may hand back pre-write data.
    """

    cache: TTLCache[dict] = TTLCache(60.0)
    calls: list = []
    old_started, old_release = threading.Event(), threading.Event()
    new_started, new_release = threading.Event(), threading.Event()
    old_build = _gated_build("old", old_started, old_release, calls)
    new_build = _gated_build("new", new_started, new_release, calls)

    with ThreadPoolExecutor(max_workers=8) as pool:
        old_leader = pool.submit(cache.get_or_build, ("k",), old_build)
        assert old_started.wait(_WAIT)
        old_waiters = [pool.submit(cache.get_or_build, ("k",), old_build) for _ in range(3)]
        waiters.wait_for(3)

        cache.clear()

        new_leader = pool.submit(cache.get_or_build, ("k",), new_build)
        assert new_started.wait(_WAIT)
        new_waiters = [pool.submit(cache.get_or_build, ("k",), new_build) for _ in range(3)]
        waiters.wait_for(6)

        # Finish the post-clear build first, then the stale one, so the stale
        # result arrives last and would win if it were allowed to store.
        new_release.set()
        assert new_leader.result(timeout=_WAIT) == {"value": "new"}
        assert all(f.result(timeout=_WAIT) == {"value": "new"} for f in new_waiters)
        old_release.set()
        assert old_leader.result(timeout=_WAIT) == {"value": "old"}
        assert all(f.result(timeout=_WAIT) == {"value": "old"} for f in old_waiters)

    # One build per side of the clear -- never one per caller.
    assert calls == ["old", "new"]
    assert cache.get_or_build(("k",), lambda: pytest.fail("should be cached")) == {"value": "new"}
