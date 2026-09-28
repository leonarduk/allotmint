from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.bootstrap.middleware import register_middleware
from backend.config import config
from backend.routes import quotes as quotes_module


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
    monkeypatch.setattr(quotes_module.config, "offline_mode", False)
    client = _make_client()

    with caplog.at_level("ERROR", logger="backend.errors"):
        resp = client.get("/api/quotes?symbols=PFE")

    assert resp.status_code == 502
    assert resp.json()["detail"] == "Upstream provider failure"
    record = caplog.records[-1]
    assert record.error_code == "provider_failure"
    assert record.provider == "yfinance"
    assert record.symbols == ["PFE"]
    assert record.provider_error == "boom"
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
    monkeypatch.setattr(quotes_module.config, "offline_mode", False)
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


def test_quotes_skips_symbol_whose_info_raises(monkeypatch):
    """A single symbol's `.info` access raising a live-fetch error must not
    prevent the other symbols' quotes from being returned (#8094)."""

    class BoomTicker:
        @property
        def info(self):
            raise RuntimeError("rate limited")

    class OkTicker:
        info = {"regularMarketPrice": 100.0, "shortName": "OK Inc", "currency": "USD"}

    def fake_tickers(symbols):
        return SimpleNamespace(tickers={"BOOM": BoomTicker(), "PFE": OkTicker()})

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", fake_tickers)
    monkeypatch.setattr(quotes_module.config, "offline_mode", False)
    client = _make_client()

    resp = client.get("/api/quotes?symbols=BOOM,PFE")
    assert resp.status_code == 200
    data = resp.json()
    assert [item["symbol"] for item in data] == ["PFE"]


def test_quotes_returns_502_when_every_symbol_fails(monkeypatch):
    """If every requested symbol's `.info` access raises, surface a
    structured 502 rather than a misleadingly successful empty list."""

    class BoomTicker:
        @property
        def info(self):
            raise RuntimeError("boom")

    def fake_tickers(symbols):
        return SimpleNamespace(tickers={"BOOM": BoomTicker()})

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", fake_tickers)
    monkeypatch.setattr(quotes_module.config, "offline_mode", False)
    client = _make_client()

    resp = client.get("/api/quotes?symbols=BOOM")
    assert resp.status_code == 502
    assert resp.json()["detail"] == "Upstream provider failure"


def test_quotes_short_circuits_when_offline_mode_enabled(monkeypatch):
    """offline_mode must skip the live yfinance call entirely (#8094)."""

    def fake_tickers(symbols):
        raise AssertionError("yfinance should not be called when offline_mode is enabled")

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", fake_tickers)
    monkeypatch.setattr(quotes_module.config, "offline_mode", True)
    client = _make_client()

    resp = client.get("/api/quotes?symbols=PFE")
    assert resp.status_code == 200
    assert resp.json() == []
