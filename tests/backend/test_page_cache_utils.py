import asyncio
import json

import pytest

from backend.utils import page_cache


@pytest.mark.asyncio
async def test_save_load_and_is_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
    assert page_cache.load_cache("p") is None
    page_cache.save_cache("p", {"a": 1})
    assert page_cache.load_cache("p") == {"a": 1}
    assert not page_cache.is_stale("p", 9999)
    assert page_cache.is_stale("missing", 1)


@pytest.mark.asyncio
async def test_schedule_refresh_and_cancel(tmp_path, monkeypatch):
    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
    calls = []

    def builder():
        calls.append(1)
        return {"v": len(calls)}

    page_cache.schedule_refresh("pg", 3600, builder)
    await asyncio.sleep(0)
    assert json.loads((tmp_path / "pg.json").read_text()) == {"v": 1}
    page_cache.schedule_refresh("pg", 3600, builder)
    assert len(page_cache._refresh_tasks) == 1
    await page_cache.cancel_refresh_tasks()
    assert page_cache._refresh_tasks == {}
