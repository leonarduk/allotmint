from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from backend.routes import market as market_module
from backend.routes.news import NewsQuotaExceeded
from backend.utils import page_cache


def _make_payload(symbol: str, label: str) -> List[dict[str, str]]:
    return [{"headline": f"{symbol} {label}", "url": f"https://example.com/{symbol.lower()}"}]


def test_fetch_headlines_uses_cached_helper(monkeypatch):
    symbols = list(market_module.INDEX_SYMBOLS.values())
    seen_fresh: set[str] = set()

    def fake_get_cached_news(symbol: str) -> List[dict[str, str]]:
        if symbol in seen_fresh:
            return _make_payload(symbol, "cached")
        seen_fresh.add(symbol)
        return _make_payload(symbol, "fresh")

    monkeypatch.setattr(market_module, "get_cached_news", fake_get_cached_news)

    first = market_module._fetch_headlines()
    second = market_module._fetch_headlines()

    assert seen_fresh == set(symbols)
    assert sorted(item["headline"] for item in first) == sorted(f"{sym} fresh" for sym in symbols)
    assert sorted(item["headline"] for item in second) == sorted(f"{sym} cached" for sym in symbols)


def test_fetch_headlines_stops_on_quota_exhaustion(monkeypatch):
    symbols = list(market_module.INDEX_SYMBOLS.values())
    stop_after = symbols[2]
    calls: list[str] = []

    def fake_get_cached_news(symbol: str) -> List[dict[str, str]]:
        calls.append(symbol)
        if symbol == stop_after:
            raise NewsQuotaExceeded("news quota exceeded")
        return _make_payload(symbol, "fresh")

    monkeypatch.setattr(market_module, "get_cached_news", fake_get_cached_news)

    headlines = market_module._fetch_headlines()

    assert calls == symbols[: symbols.index(stop_after) + 1]
    assert all(stop_after not in item["headline"] for item in headlines)
    assert all(item["headline"].endswith("fresh") for item in headlines)


def test_fetch_headlines_status_explains_an_empty_list(monkeypatch):
    """An empty feed says why: quota exhausted vs no source answered (#7788)."""

    def quota(_symbol: str) -> List[dict[str, str]]:
        raise NewsQuotaExceeded("news quota exceeded")

    monkeypatch.setattr(market_module, "get_cached_news", quota)
    headlines = market_module._fetch_headlines()
    assert headlines == [] and headlines.status == "quota_exhausted"

    monkeypatch.setattr(market_module, "get_cached_news", lambda _symbol: [])
    headlines = market_module._fetch_headlines()
    assert headlines == [] and headlines.status == "unavailable"

    monkeypatch.setattr(market_module, "get_cached_news", lambda s: _make_payload(s, "fresh"))
    assert market_module._fetch_headlines().status == "ok"


def test_fetch_headlines_partial_data_before_quota_is_ok(monkeypatch):
    symbols = list(market_module.INDEX_SYMBOLS.values())

    def fake_get_cached_news(symbol: str) -> List[dict[str, str]]:
        if symbol == symbols[1]:
            raise NewsQuotaExceeded("news quota exceeded")
        return _make_payload(symbol, "fresh")

    monkeypatch.setattr(market_module, "get_cached_news", fake_get_cached_news)
    assert market_module._fetch_headlines().status == "ok"


def test_fetch_headlines_skips_symbol_on_unexpected_error(monkeypatch):
    """A non-quota error for one symbol must not be mistaken for quota
    exhaustion and abort the remaining symbols."""

    symbols = list(market_module.INDEX_SYMBOLS.values())
    failing = symbols[0]
    calls: list[str] = []

    def fake_get_cached_news(symbol: str) -> list[dict[str, str]]:
        calls.append(symbol)
        if symbol == failing:
            raise RuntimeError("no running event loop")
        return _make_payload(symbol, "fresh")

    monkeypatch.setattr(market_module, "get_cached_news", fake_get_cached_news)

    headlines = market_module._fetch_headlines()

    assert calls == symbols
    expected = sorted(f"{sym} fresh" for sym in symbols[1:])
    assert sorted(item["headline"] for item in headlines) == expected


def test_fetch_headlines_serves_fresh_cache_off_event_loop_thread(monkeypatch, tmp_path):
    """Regression: ``market_overview`` runs ``_fetch_headlines`` on a worker
    thread with no event loop. Scheduling the background cache refresh there
    used to raise ``RuntimeError`` and blank every headline."""

    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(market_module, "INDEX_SYMBOLS", {"One": "ONE"})
    page_cache.save_cache("news_ONE", _make_payload("ONE", "cached"))

    with ThreadPoolExecutor(max_workers=1) as pool:
        headlines = pool.submit(market_module._fetch_headlines).result()

    assert [item["headline"] for item in headlines] == ["ONE cached"]
    assert "news_ONE" not in page_cache._refresh_tasks


@pytest.mark.asyncio
async def test_market_overview_selects_region(monkeypatch):
    indexes_result = {"S&P 500": {"value": 4300.0, "change": 1.2}}
    sectors_by_region = {
        "us": [{"sector": "Technology", "change": 0.5, "source": "etf"}],
        "uk": [{"sector": "Financials", "change": -0.3, "source": "basket"}],
    }
    headlines_result = [{"headline": "Example", "url": "https://example.com"}]
    regions: list[str] = []

    def fake_fetch_region_sectors(region):
        regions.append(region)
        return sectors_by_region[region]

    monkeypatch.setattr(market_module.cfg, "default_sector_region", "US", raising=False)
    monkeypatch.setattr(market_module, "_fetch_indexes", lambda: indexes_result)
    monkeypatch.setattr(market_module.market_sectors, "fetch_region_sectors", fake_fetch_region_sectors)
    monkeypatch.setattr(market_module, "_fetch_headlines", lambda: headlines_result)

    result_default = await market_module.market_overview()

    assert regions == ["us"]
    assert result_default == {
        "indexes": indexes_result,
        "sectors": sectors_by_region["us"],
        "headlines": headlines_result,
        "headlines_status": "ok",
    }

    regions.clear()
    result_uk = await market_module.market_overview(region="uk")

    assert regions == ["uk"]
    assert result_uk["sectors"] == sectors_by_region["uk"]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize("value", [None, "", 123])
def test_parse_published_at_rejects_missing_or_non_string_values(value):
    assert market_module._parse_published_at(value) is None


def test_parse_published_at_accepts_utc_suffix():
    assert market_module._parse_published_at("2026-07-29T10:30:00Z") == datetime(
        2026, 7, 29, 10, 30, tzinfo=timezone.utc
    )


def test_headline_max_age_uses_environment_override(monkeypatch):
    monkeypatch.setenv("HEADLINE_MAX_AGE_HOURS", "24")

    assert market_module._get_headline_max_age() == timedelta(hours=24)


def test_headline_max_age_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv("HEADLINE_MAX_AGE_HOURS", raising=False)

    assert market_module._get_headline_max_age() == timedelta(hours=72)


@pytest.mark.parametrize("value", ["invalid", "0", "-1", "nan", "inf"])
def test_headline_max_age_falls_back_for_invalid_values(monkeypatch, value):
    monkeypatch.setenv("HEADLINE_MAX_AGE_HOURS", value)

    assert market_module._get_headline_max_age() == timedelta(hours=72)


def test_sort_and_filter_headlines_excludes_old_and_sorts_newest_first():
    now = datetime.now(timezone.utc)
    old = {
        "headline": "Old",
        "url": "https://example.com/old",
        "published_at": _iso(now - timedelta(days=10)),
    }
    middle = {
        "headline": "Middle",
        "url": "https://example.com/middle",
        "published_at": _iso(now - timedelta(hours=10)),
    }
    newest = {
        "headline": "Newest",
        "url": "https://example.com/newest",
        "published_at": _iso(now - timedelta(hours=1)),
    }

    result = market_module._sort_and_filter_headlines([old, middle, newest])

    assert result == [newest, middle]


def test_sort_and_filter_headlines_excludes_undated_when_recent_items_exist():
    now = datetime.now(timezone.utc)
    recent = {
        "headline": "Recent",
        "url": "https://example.com/recent",
        "published_at": _iso(now - timedelta(hours=1)),
    }
    old = {
        "headline": "Old",
        "url": "https://example.com/old",
        "published_at": _iso(now - timedelta(days=10)),
    }
    undated = {"headline": "Undated", "url": "https://example.com/undated"}

    result = market_module._sort_and_filter_headlines([undated, old, recent])

    assert result == [recent]


def test_sort_and_filter_headlines_falls_back_when_nothing_recent():
    now = datetime.now(timezone.utc)
    old = {
        "headline": "Old",
        "url": "https://example.com/old",
        "published_at": _iso(now - timedelta(days=30)),
    }
    older = {
        "headline": "Older",
        "url": "https://example.com/older",
        "published_at": _iso(now - timedelta(days=60)),
    }
    undated = {"headline": "Undated", "url": "https://example.com/undated"}

    result = market_module._sort_and_filter_headlines([older, old, undated])

    assert result == [old, older, undated]


def test_sort_and_filter_headlines_keeps_undated_when_no_dated_items():
    undated = [{"headline": "A", "url": "https://example.com/a"}]

    assert market_module._sort_and_filter_headlines(undated) == undated
