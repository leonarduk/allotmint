from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import screener as screener_module
from backend.routes import screener
from backend.utils import page_cache


def _client():
    app = FastAPI()
    app.include_router(screener.router)
    return TestClient(app)


def test_screener_success(monkeypatch):
    client = _client()
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "is_stale", lambda p, ttl: True)
    monkeypatch.setattr(page_cache, "load_cache", lambda p: None)
    saved = {}
    monkeypatch.setattr(page_cache, "save_cache", lambda p, d: saved.setdefault("data", d))

    monkeypatch.setattr(
        screener,
        "screen",
        lambda symbols, **k: [SimpleNamespace(model_dump=lambda: {"ticker": symbols[0]})],
    )
    resp = client.get("/screener", params={"tickers": "ABC"})
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["ticker"] == "ABC"
    assert saved["data"][0]["ticker"] == "ABC"


def test_screener_uses_cache(monkeypatch):
    client = _client()
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "is_stale", lambda p, ttl: False)
    monkeypatch.setattr(page_cache, "load_cache", lambda p: [{"ticker": "C"}])
    called = False

    def _screen(*args, **kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(screener, "screen", _screen)
    resp = client.get("/screener", params={"tickers": "ABC"})
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["ticker"] == "C"
    assert not called


def test_screener_no_tickers(monkeypatch):
    client = _client()
    resp = client.get("/screener", params={"tickers": " , "})
    assert resp.status_code == 400


def test_screener_value_error(monkeypatch):
    client = _client()
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "is_stale", lambda p, ttl: True)
    monkeypatch.setattr(page_cache, "load_cache", lambda p: None)
    monkeypatch.setattr(
        screener,
        "screen",
        lambda symbols, **k: (_ for _ in ()).throw(ValueError("bad")),
    )
    resp = client.get("/screener", params={"tickers": "ABC"})
    assert resp.status_code == 400


def test_fetch_fundamentals_prefers_yahoo(monkeypatch):
    monkeypatch.setattr(screener_module, "_CACHE", {})

    class DummyTicker:
        def __init__(self, symbol):
            self.symbol = symbol
            self.info = {
                "shortName": "Yahoo Corp",
                "pegRatio": 1.5,
                "trailingPE": 20.1,
                "debtToEquity": 1.0,
                "longTermDebtToEquity": 0.5,
                "interestCoverage": 4.2,
                "currentRatio": 2.1,
                "quickRatio": 1.8,
                "freeCashflow": 123456789,
                "trailingEps": 3.21,
                "grossMargins": 0.52,
                "operatingMargins": 0.41,
                "profitMargins": 0.33,
                "ebitdaMargins": 0.37,
                "returnOnAssets": 0.11,
                "returnOnEquity": 0.18,
                "returnOnInvestment": 0.09,
                "dividendYield": 0.012,
                "payoutRatio": 0.34,
                "beta": 0.9,
                "sharesOutstanding": 1000000,
                "floatShares": 900000,
                "marketCap": 500000000,
                "fiftyTwoWeekHigh": 150.0,
                "fiftyTwoWeekLow": 75.0,
                "averageDailyVolume10Day": 12345,
            }

    def fail_alpha(*args, **kwargs):  # pragma: no cover - ensures no fallback usage
        pytest.fail("Alpha Vantage should not be invoked when Yahoo data is sufficient")

    monkeypatch.setattr(screener_module.yf, "Ticker", DummyTicker)
    monkeypatch.setattr(screener_module.requests, "get", fail_alpha)

    result = screener_module.fetch_fundamentals("aapl")

    assert result.ticker == "AAPL"
    assert result.name == "Yahoo Corp"
    assert result.peg_ratio == pytest.approx(1.5)
    assert result.market_cap == 500000000

    cache_key = ("AAPL", date.today().isoformat())
    assert screener_module._CACHE[cache_key][1] is result


def test_fetch_fundamentals_falls_back_to_alpha(monkeypatch):
    monkeypatch.setattr(screener_module, "_CACHE", {})

    ticker_calls = []

    class EmptyTicker:
        def __init__(self, symbol):
            ticker_calls.append(symbol)
            self.info = {}

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):  # pragma: no cover - no-op in tests
            return None

        def json(self):
            return self._payload

    alpha_calls = []

    def fake_get(url, params, timeout):
        alpha_calls.append((url, params))
        assert params["symbol"] == "AAPL"
        return DummyResponse(
            {
                "Name": "Alpha Co",
                "PEG": "1.1",
                "PERatio": "18.2",
                "MarketCapitalization": "123456",
                "SharesOutstanding": "654321",
            }
        )

    monkeypatch.setattr(screener_module.yf, "Ticker", EmptyTicker)
    monkeypatch.setattr(screener_module.requests, "get", fake_get)

    result = screener_module.fetch_fundamentals("AAPL")

    assert ticker_calls == ["AAPL"]
    assert len(alpha_calls) == 1
    assert result.name == "Alpha Co"
    assert result.market_cap == 123456

    cache_key = ("AAPL", date.today().isoformat())
    assert screener_module._CACHE[cache_key][1] is result
