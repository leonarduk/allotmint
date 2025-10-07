from __future__ import annotations

from typing import List

import pytest

from backend.routes import market as market_module


def _make_payload(symbol: str, label: str) -> List[dict[str, str]]:
    return [{"headline": f"{symbol} {label}", "url": f"https://example.com/{symbol.lower()}"}]


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


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
    assert sorted(item["headline"] for item in first) == sorted(
        f"{sym} fresh" for sym in symbols
    )
    assert sorted(item["headline"] for item in second) == sorted(
        f"{sym} cached" for sym in symbols
    )


def test_fetch_headlines_stops_on_quota_exhaustion(monkeypatch):
    symbols = list(market_module.INDEX_SYMBOLS.values())
    stop_after = symbols[2]
    calls: list[str] = []

    def fake_get_cached_news(symbol: str) -> List[dict[str, str]]:
        calls.append(symbol)
        if symbol == stop_after:
            raise RuntimeError("news quota exceeded")
        return _make_payload(symbol, "fresh")

    monkeypatch.setattr(market_module, "get_cached_news", fake_get_cached_news)

    headlines = market_module._fetch_headlines()

    assert calls == symbols[: symbols.index(stop_after) + 1]
    assert all(stop_after not in item["headline"] for item in headlines)
    assert all(
        item["headline"].endswith("fresh")
        for item in headlines
    )


@pytest.mark.asyncio
async def test_market_overview_selects_region(monkeypatch):
    calls: list[object] = []

    indexes_result = {"S&P 500": {"value": 4300.0, "change": 1.2}}
    sectors_us = [{"sector": "US Tech", "change": 0.5}]
    sectors_uk = [{"sector": "UK Banks", "change": -0.3}]
    headlines_result = [{"headline": "Example", "url": "https://example.com"}]

    def tracking_safe(func, default):
        try:
            result = func()
        except Exception:
            return default
        calls.append(func)
        return result

    def fake_fetch_indexes():
        return indexes_result

    def fake_fetch_sectors():
        return sectors_us

    def fake_fetch_uk_sectors():
        return sectors_uk

    def fake_fetch_headlines():
        return headlines_result

    monkeypatch.setattr(market_module, "_safe", tracking_safe)
    monkeypatch.setattr(market_module, "_fetch_indexes", fake_fetch_indexes)
    monkeypatch.setattr(market_module, "_fetch_sectors", fake_fetch_sectors)
    monkeypatch.setattr(market_module, "_fetch_uk_sectors", fake_fetch_uk_sectors)
    monkeypatch.setattr(market_module, "_fetch_headlines", fake_fetch_headlines)

    result_default = await market_module.market_overview()

    assert fake_fetch_sectors in calls
    assert fake_fetch_uk_sectors not in calls
    assert result_default == {
        "indexes": indexes_result,
        "sectors": sectors_us,
        "headlines": headlines_result,
    }

    calls.clear()

    result_uk = await market_module.market_overview(region="uk")

    assert fake_fetch_uk_sectors in calls
    assert fake_fetch_sectors not in calls
    assert result_uk == {
        "indexes": indexes_result,
        "sectors": sectors_uk,
        "headlines": headlines_result,
    }


def test_fetch_uk_sectors_flat_dict(monkeypatch):
    payload = {"Energy": "1.2%", "Industrials": -0.5}
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return DummyResponse(payload)

    monkeypatch.setattr(market_module.requests, "get", fake_get)

    result = market_module._fetch_uk_sectors()

    assert calls
    assert calls[0][1]["timeout"] == 10
    assert result == [
        {"sector": "Energy", "change": 1.2},
        {"sector": "Industrials", "change": -0.5},
    ]


def test_fetch_uk_sectors_nested_values(monkeypatch):
    payload = {
        "items": [
            {"name": "Energy", "values": {"percentChange": "2.3%"}},
            {"sector": "Financials", "values": {"pct": -1.1}},
            {"label": "Utilities", "values": {"change": "0.5"}},
        ]
    }

    def fake_get(*_, **__):
        return DummyResponse(payload)

    monkeypatch.setattr(market_module.requests, "get", fake_get)

    result = market_module._fetch_uk_sectors()

    assert result == [
        {"sector": "Energy", "change": 2.3},
        {"sector": "Financials", "change": -1.1},
        {"sector": "Utilities", "change": 0.5},
    ]


def test_fetch_uk_sectors_skips_invalid_entries(monkeypatch):
    payload = [
        {"percentChange": 1.0},
        {"name": "", "percentChange": "2.0"},
        {"name": "Real Estate", "percentChange": "n/a"},
        {"name": "Healthcare", "percentChange": "3.5%"},
    ]

    def fake_get(*_, **__):
        return DummyResponse(payload)

    monkeypatch.setattr(market_module.requests, "get", fake_get)

    result = market_module._fetch_uk_sectors()

    assert result == [{"sector": "Healthcare", "change": 3.5}]
