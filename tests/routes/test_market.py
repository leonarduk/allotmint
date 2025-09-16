import logging
from types import SimpleNamespace

import pytest
import requests

from backend.routes import market, news


def test_fetch_indexes(monkeypatch):
    class FakeTicker:
        def __init__(self, info):
            self.info = info

    def fake_Tickers(symbols):
        tickers = {}
        for i, (name, sym) in enumerate(market.INDEX_SYMBOLS.items(), start=1):
            tickers[sym] = FakeTicker(
                {
                    "regularMarketPrice": 100 * i,
                    "regularMarketChangePercent": i,
                }
            )
        return SimpleNamespace(tickers=tickers)

    monkeypatch.setattr(market.yf, "Tickers", fake_Tickers)

    result = market._fetch_indexes()
    expected = {}
    for i, name in enumerate(market.INDEX_SYMBOLS.keys(), start=1):
        expected[name] = {"value": float(100 * i), "change": float(i)}
    assert result == expected


def test_fetch_sectors(monkeypatch):
    class DummyResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "Rank A: Real-Time Performance": {
                    "Technology": "1.23%",
                    "Invalid": "not-a-number",
                }
            }

    def fake_get(url, params, timeout):
        return DummyResponse()

    monkeypatch.setattr(market.requests, "get", fake_get)

    assert market._fetch_sectors() == [{"sector": "Technology", "change": 1.23}]


def test_fetch_uk_sectors(monkeypatch):
    class DummyResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "sectors": [
                    {"name": "Technology", "percentChange": "1.23%"},
                    {"sectorName": "Industrials", "change": -0.5},
                    {"name": "Invalid", "percentChange": "oops"},
                ]
            }

    def fake_get(url, headers=None, timeout=10):
        return DummyResponse()

    monkeypatch.setattr(market.requests, "get", fake_get)

    assert market._fetch_uk_sectors() == [
        {"sector": "Technology", "change": 1.23},
        {"sector": "Industrials", "change": -0.5},
    ]


def test_fetch_headlines_fallback(monkeypatch):
    def fake_get(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr(news.requests, "get", fake_get)
    monkeypatch.setattr(
        news, "fetch_news_yahoo", lambda t: [{"url": "u1", "headline": "h1"}]
    )

    headlines = market._fetch_headlines()
    assert headlines == [{"url": "u1", "headline": "h1"}]


def test_fetch_headlines_dedup(monkeypatch):
    calls = [
        [
            {"url": "u1", "headline": "h1"},
            {"url": "u1", "headline": "h1 duplicate"},
            {"headline": "h2"},
            {"headline": "h2"},
        ],
        [{"url": "u3", "headline": "h3"}],
        [],
        [],
        [],
    ]

    def fake_fetch_news(sym):
        return calls.pop(0)

    monkeypatch.setattr(market, "_fetch_news", fake_fetch_news)

    headlines = market._fetch_headlines()
    assert headlines == [
        {"url": "u1", "headline": "h1"},
        {"headline": "h2"},
        {"url": "u3", "headline": "h3"},
    ]


def test_fetch_headlines_logs_error(monkeypatch, caplog):
    monkeypatch.setattr(market, "_fetch_news", lambda sym: [])
    with caplog.at_level(logging.ERROR):
        headlines = market._fetch_headlines()
    assert headlines == []
    assert "Failed to fetch news for all index symbols" in caplog.text


def test_safe_returns_default_on_exception():
    def boom():
        raise RuntimeError("boom")

    assert market._safe(boom, "default") == "default"


@pytest.mark.asyncio
async def test_market_overview_region_switch(monkeypatch):
    monkeypatch.setattr(market.cfg, "default_sector_region", "US", raising=False)
    monkeypatch.setattr(market, "_safe", lambda func, default: func())
    monkeypatch.setattr(market, "_fetch_indexes", lambda: {"S&P 500": {"value": 1, "change": 0.1}})
    monkeypatch.setattr(market, "_fetch_headlines", lambda: [])
    monkeypatch.setattr(market, "_fetch_sectors", lambda: [{"sector": "US", "change": 1.0}])
    monkeypatch.setattr(market, "_fetch_uk_sectors", lambda: [{"sector": "UK", "change": 2.0}])

    result = await market.market_overview(region="uk")

    assert result["sectors"] == [{"sector": "UK", "change": 2.0}]


@pytest.mark.asyncio
async def test_market_overview_config_default(monkeypatch):
    monkeypatch.setattr(market.cfg, "default_sector_region", "uk", raising=False)
    monkeypatch.setattr(market, "_safe", lambda func, default: func())
    monkeypatch.setattr(market, "_fetch_indexes", lambda: {})
    monkeypatch.setattr(market, "_fetch_headlines", lambda: [])
    monkeypatch.setattr(market, "_fetch_sectors", lambda: [{"sector": "US", "change": 1.0}])
    monkeypatch.setattr(market, "_fetch_uk_sectors", lambda: [{"sector": "UK", "change": 2.0}])

    result = await market.market_overview()

    assert result["sectors"] == [{"sector": "UK", "change": 2.0}]
