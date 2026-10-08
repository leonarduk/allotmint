import asyncio
import logging
import os
import time
from pathlib import Path

from backend.utils import page_cache


async def _wait_for_cache(page_name, timeout=2.0):
    """Poll until ``page_name`` is cached; retries now back off, so a fixed sleep is racy."""
    deadline = time.monotonic() + timeout
    while page_cache.load_cache(page_name) is None and time.monotonic() < deadline:
        await asyncio.sleep(0.01)


def test_async_builder(monkeypatch, tmp_path):
    async def run():
        monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)

        async def builder():
            return {"value": 1}

        page_cache.schedule_refresh("async_page", 0, builder)
        await asyncio.sleep(0.05)
        assert page_cache.load_cache("async_page") == {"value": 1}
        await page_cache.cancel_refresh_tasks()

    asyncio.run(run())


def test_schedule_refresh_on_loop_after_off_loop_call_still_schedules(monkeypatch, tmp_path):
    """The no-loop guard must not stop a later on-loop call from scheduling."""

    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)

    page_cache.schedule_refresh("guard_page", 60, lambda: {"value": 1})
    assert "guard_page" not in page_cache._refresh_tasks

    async def run():
        page_cache.schedule_refresh("guard_page", 60, lambda: {"value": 1})
        assert "guard_page" in page_cache._refresh_tasks
        await asyncio.sleep(0.01)  # let the task start before cancelling it
        await page_cache.cancel_refresh_tasks()

    asyncio.run(run())


def test_builder_error_logged_and_continues(monkeypatch, tmp_path, caplog):
    async def run():
        monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)

        calls = {"count": 0}

        def builder():
            calls["count"] += 1
            if calls["count"] == 1:
                raise ValueError("boom")
            return {"ok": True}

        page_cache.schedule_refresh("error_page", 0.01, builder)
        await _wait_for_cache("error_page")
        await page_cache.cancel_refresh_tasks()
        assert page_cache.load_cache("error_page") == {"ok": True}

    with caplog.at_level("ERROR"):
        asyncio.run(run())

    assert "Cache refresh failed for error_page" in caplog.text


def test_load_cache_handles_oserror(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
    page_name = "oserror_page"
    path = tmp_path / f"{page_name}.json"
    path.write_text("{}")

    original_open = Path.open

    def fake_open(self, *args, **kwargs):
        if self == path:
            raise OSError("boom")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)

    with caplog.at_level("ERROR"):
        assert page_cache.load_cache(page_name) is None

    assert f"Cache load failed for {page_name}" in caplog.text


def test_first_builder_exception_cache_persisted(monkeypatch, tmp_path):
    async def run():
        monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)

        calls = {"builder": 0, "save": 0}

        def builder():
            calls["builder"] += 1
            if calls["builder"] == 1:
                raise ValueError("boom")
            return {"ok": True}

        original_save = page_cache.save_cache

        def flaky_save(page_name, data):
            calls["save"] += 1
            if calls["save"] == 1:
                raise OSError("disk full")
            return original_save(page_name, data)

        monkeypatch.setattr(page_cache, "save_cache", flaky_save)

        page_cache.schedule_refresh("error_page", 0.01, builder)
        await _wait_for_cache("error_page")
        await page_cache.cancel_refresh_tasks()

        assert page_cache.load_cache("error_page") == {"ok": True}
        assert calls["builder"] >= 2
        assert calls["save"] >= 2

    asyncio.run(run())


def test_load_cache_invalid_json(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
    page_name = "bad_json"
    path = tmp_path / f"{page_name}.json"
    path.write_text("{not:json}")
    with caplog.at_level("ERROR"):
        assert page_cache.load_cache(page_name) is None
    assert f"Cache load failed for {page_name}" in caplog.text


def test_is_stale(monkeypatch, tmp_path):
    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
    page_name = "stale_page"
    path = tmp_path / f"{page_name}.json"
    path.write_text("{}")
    assert page_cache.is_stale(page_name, ttl=1000) is False
    old = time.time() - 2000
    os.utime(path, (old, old))
    assert page_cache.is_stale(page_name, ttl=1000) is True


def test_schedule_refresh_can_refresh_false(monkeypatch, tmp_path):
    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
    called = False

    def builder():
        nonlocal called
        called = True
        return {}

    page_cache.schedule_refresh("never", 0, builder, can_refresh=lambda: False)
    assert "never" not in page_cache._refresh_tasks
    assert called is False


def test_schedule_refresh_idempotent(monkeypatch, tmp_path):
    async def run():
        monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)

        def builder():
            return {}

        page_cache.schedule_refresh("page", 0.01, builder)
        first = list(page_cache._refresh_tasks)
        page_cache.schedule_refresh("page", 0.01, builder)
        assert list(page_cache._refresh_tasks) == first
        try:
            await page_cache.cancel_refresh_tasks()
        except asyncio.CancelledError:
            pass

    asyncio.run(run())


def test_schedule_refresh_initial_delay(monkeypatch, tmp_path):
    async def run():
        monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)

        calls = {"count": 0}

        def builder():
            calls["count"] += 1
            return {}

        page_cache.schedule_refresh("delayed", 0.05, builder, initial_delay=0.05)
        await asyncio.sleep(0.02)
        assert calls["count"] == 0
        await asyncio.sleep(0.05)
        assert calls["count"] >= 1
        await page_cache.cancel_refresh_tasks()

    asyncio.run(run())


def test_builder_returns_awaitable_and_save_error_backs_off(monkeypatch, tmp_path, caplog):
    """A build returning an awaitable is awaited; a failing save backs off instead of spinning."""
    monkeypatch.setattr(page_cache, "_RETRY_BASE_SECONDS", 0.05)

    async def run():
        monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)

        async def builder_async():
            return {"ok": True}

        saved = []

        def failing_save(page_name, data):
            saved.append(data)
            raise OSError("disk full")

        monkeypatch.setattr(page_cache, "save_cache", failing_save)
        page_cache.schedule_refresh("x", 10, lambda: builder_async())
        await asyncio.sleep(0.2)
        await page_cache.cancel_refresh_tasks()
        return saved

    with caplog.at_level(logging.ERROR):
        saved = asyncio.run(run())

    # Retries at ~0, 0.05, 0.15s within the 0.2s window -- not thousands.
    assert 2 <= len(saved) <= 4
    assert all(data == {"ok": True} for data in saved)
    assert "Cache refresh failed for x (attempt 2)" in caplog.text


def test_always_failing_builder_backs_off(monkeypatch, tmp_path):
    """A builder that never succeeds is retried with exponential backoff (#10362)."""
    monkeypatch.setattr(page_cache, "_RETRY_BASE_SECONDS", 0.02)

    async def run():
        monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
        calls = []

        def builder():
            calls.append(time.monotonic())
            raise ValueError("always broken")

        page_cache.schedule_refresh("broken", 60, builder)
        await asyncio.sleep(0.5)
        await page_cache.cancel_refresh_tasks()
        return calls

    calls = asyncio.run(run())

    # Delays 0.02, 0.04, 0.08, 0.16 -> about 5 calls in 0.5s; sleep(0) made thousands.
    assert 3 <= len(calls) <= 7
    gaps = [later - earlier for earlier, later in zip(calls, calls[1:], strict=False)]
    assert gaps[-1] > gaps[0]


def test_retry_delay_doubles_and_is_capped_by_ttl():
    base = page_cache._RETRY_BASE_SECONDS
    assert page_cache._retry_delay(3600, 1) == base
    assert page_cache._retry_delay(3600, 3) == base * 4
    assert page_cache._retry_delay(30, 10) == 30
    assert page_cache._retry_delay(0, 1) == page_cache._RETRY_MIN_SECONDS
    assert page_cache._retry_delay(3600, 10_000) == 3600


def test_cancel_refresh_tasks_handles_error():
    class FakeTask:
        def cancel(self):
            self.cancelled = True

        def get_loop(self):
            return asyncio.get_running_loop()

        def __await__(self):
            raise ValueError("boom")

    async def run():
        page_cache._refresh_tasks = {"fake": FakeTask()}
        await page_cache.cancel_refresh_tasks()

    asyncio.run(run())


def test_schedule_refresh_without_running_loop_is_noop(monkeypatch, tmp_path):
    # Sync FastAPI handlers run in a worker thread with no event loop; this
    # must not raise or the handler fails after its data was fetched.
    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)

    page_cache.schedule_refresh("no_loop_page", 60, lambda: {"value": 1})

    assert "no_loop_page" not in page_cache._refresh_tasks
