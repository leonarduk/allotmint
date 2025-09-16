"""Tests for the market overview helpers and HTTP endpoint."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import market


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(market.router)
    return TestClient(app)


def test_fetch_indexes_with_mocked_yfinance(monkeypatch):
    symbols = list(market.INDEX_SYMBOLS.items())
    last_symbol = symbols[-1][1]

    def fake_tickers(requested: str) -> SimpleNamespace:
        assert requested == " ".join(market.INDEX_SYMBOLS.values())
        tickers = {}
        for idx, (name, sym) in enumerate(symbols, start=1):
            info = {
                "regularMarketPrice": idx * 100,
                "regularMarketChangePercent": idx / 10 if idx % 2 else None,
            }
            if sym == last_symbol:
                info["regularMarketPrice"] = None
            tickers[sym] = SimpleNamespace(info=info)
        return SimpleNamespace(tickers=tickers)

    monkeypatch.setattr(market.yf, "Tickers", fake_tickers)

    result = market._fetch_indexes()

    expected = {}
    for idx, (name, sym) in enumerate(symbols, start=1):
        if sym == last_symbol:
            continue
        expected[name] = {
            "value": float(idx * 100),
            "change": float(idx / 10) if idx % 2 else None,
        }

    assert result == expected


def test_fetch_sectors_with_mocked_requests(monkeypatch):
    monkeypatch.setattr(market.cfg, "alpha_vantage_key", "abc123", raising=False)
    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            captured["status_called"] = True

        def json(self):
            return {
                "Rank A: Real-Time Performance": {
                    "Technology": "1.23%",
                    "Energy": "-0.50%",
                    "Invalid": "??",
                }
            }

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(market.requests, "get", fake_get)

    sectors = market._fetch_sectors()

    assert captured == {
        "url": "https://www.alphavantage.co/query",
        "params": {"function": "SECTOR", "apikey": "abc123"},
        "timeout": 10,
        "status_called": True,
    }
    assert sectors == [
        {"sector": "Technology", "change": 1.23},
        {"sector": "Energy", "change": -0.5},
    ]


def test_fetch_uk_sectors_with_mocked_requests(monkeypatch):
    monkeypatch.setattr(
        market.cfg,
        "uk_sector_endpoint",
        "https://example.test/sectors",
        raising=False,
    )
    monkeypatch.setattr(
        market.cfg, "selenium_user_agent", "Agent/1.0", raising=False
    )
    captured = {}
    payload = [
        {"name": "Technology", "percentChange": "1.0%"},
        {"sectorName": "Industrials", "change": -0.3},
        {"sector": "Financials", "values": {"percentChange": "0.75%"}},
        {"label": "Ignored", "percentChange": None},
        "bad",
    ]

    class DummyResponse:
        def raise_for_status(self):
            captured["status_called"] = True

        def json(self):
            return {"items": payload}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(market.requests, "get", fake_get)

    sectors = market._fetch_uk_sectors()

    assert captured == {
        "url": "https://example.test/sectors",
        "headers": {"User-Agent": "Agent/1.0"},
        "timeout": 10,
        "status_called": True,
    }
    assert sectors == [
        {"sector": "Technology", "change": 1.0},
        {"sector": "Industrials", "change": -0.3},
        {"sector": "Financials", "change": 0.75},
    ]


def test_fetch_headlines_with_mocked_news(monkeypatch):
    monkeypatch.setattr(market, "INDEX_SYMBOLS", {"One": "ONE", "Two": "TWO"})
    calls = []
    responses = {
        "ONE": [
            {"url": "https://example.test/1", "headline": "First"},
            {"url": "https://example.test/1", "headline": "Duplicate url"},
            {"headline": "Second"},
        ],
        "TWO": [
            {"headline": "Second"},
            {"url": "https://example.test/3", "headline": "Third"},
            {},
        ],
    }

    def fake_get_cached_news(symbol):
        calls.append(symbol)
        return responses[symbol]

    monkeypatch.setattr(market, "get_cached_news", fake_get_cached_news)

    headlines = market._fetch_headlines()

    assert calls == ["ONE", "TWO"]
    assert headlines == [
        {"url": "https://example.test/1", "headline": "First"},
        {"headline": "Second"},
        {"url": "https://example.test/3", "headline": "Third"},
    ]


def test_market_overview_default_region_handles_fetch_failures(monkeypatch):
    client = _client()
    monkeypatch.setattr(market.cfg, "default_sector_region", "US", raising=False)
    monkeypatch.setattr(
        market, "_fetch_uk_sectors", lambda: pytest.fail("UK sectors fetch should not be used")
    )
    calls = []

    def boom_indexes():
        calls.append("indexes")
        raise RuntimeError("boom indexes")

    def boom_sectors():
        calls.append("sectors")
        raise RuntimeError("boom sectors")

    def boom_headlines():
        calls.append("headlines")
        raise RuntimeError("boom headlines")

    monkeypatch.setattr(market, "_fetch_indexes", boom_indexes)
    monkeypatch.setattr(market, "_fetch_sectors", boom_sectors)
    monkeypatch.setattr(market, "_fetch_headlines", boom_headlines)

    resp = client.get("/market/overview")
    assert resp.status_code == 200
    assert resp.json() == {"indexes": {}, "sectors": [], "headlines": []}
    assert calls == ["indexes", "sectors", "headlines"]


def test_market_overview_uk_region_handles_fetch_errors(monkeypatch):
    client = _client()
    monkeypatch.setattr(market.cfg, "default_sector_region", "US", raising=False)

    monkeypatch.setattr(
        market,
        "_fetch_indexes",
        lambda: {"Dow Jones": {"value": 100.0, "change": 1.5}},
    )
    monkeypatch.setattr(
        market, "_fetch_sectors", lambda: pytest.fail("US sector fetch should not be used")
    )
    calls = []

    def boom_uk():
        calls.append("uk")
        raise RuntimeError("boom uk")

    def boom_headlines():
        calls.append("headlines")
        raise RuntimeError("boom headlines")

    monkeypatch.setattr(market, "_fetch_uk_sectors", boom_uk)
    monkeypatch.setattr(market, "_fetch_headlines", boom_headlines)

    resp = client.get("/market/overview", params={"region": "UK"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["indexes"] == {"Dow Jones": {"value": 100.0, "change": 1.5}}
    assert data["sectors"] == []
    assert data["headlines"] == []
    assert calls == ["uk", "headlines"]
