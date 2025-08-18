import asyncio

import pytest

from backend.utils import page_cache


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
        await asyncio.sleep(0.03)
        await page_cache.cancel_refresh_tasks()
        assert page_cache.load_cache("error_page") == {"ok": True}

    with caplog.at_level("ERROR"):
        asyncio.run(run())

    assert "Cache refresh failed for error_page" in caplog.text
