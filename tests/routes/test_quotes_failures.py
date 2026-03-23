from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import quotes as quotes_module
from backend.bootstrap.middleware import register_middleware
from backend.config import config


def _make_client():
    """Create a minimal app with the quotes router and the AppError middleware."""
    app = FastAPI()
    register_middleware(app, config)
    app.include_router(quotes_module.router)
    return TestClient(app)


def test_quotes_returns_502_on_yfinance_error(monkeypatch, caplog):
    def mock_tickers(symbols):
        raise RuntimeError("boom")

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", mock_tickers)
    client = _make_client()

    with caplog.at_level("ERROR", logger="backend.errors"):
        resp = client.get("/api/quotes?symbols=PFE")

    assert resp.status_code == 502
    assert resp.json()["detail"].startswith("Failed to fetch quotes")
    record = caplog.records[-1]
    assert record.error_code == "provider_failure"
    assert record.provider == "yfinance"
    assert record.symbols == ["PFE"]
    assert record.path == "/api/quotes"


def test_quotes_excludes_missing_regular_market_price(monkeypatch):
    class FakeTicker:
        def __init__(self, info):
            self.info = info

    def fake_tickers(symbols):
        return SimpleNamespace(
            tickers={
                "PFE": FakeTicker({"regularMarketPrice": 100.0}),
                "MSFT": FakeTicker({}),
            }
        )

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", fake_tickers)
    client = _make_client()

    resp = client.get("/api/quotes?symbols=PFE,MSFT")
    assert resp.status_code == 200
    data = resp.json()
    assert [item["symbol"] for item in data] == ["PFE"]


def test_quotes_no_symbols_returns_empty_list():
    client = _make_client()
    resp = client.get("/api/quotes?symbols=")
    assert resp.status_code == 200
    assert resp.json() == []
