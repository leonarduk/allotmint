from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.bootstrap.middleware import register_middleware
from backend.config import config
from backend.routes import quotes as quotes_module
from tests.yahoo_chart_fakes import FakeChartTicker


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
    def fake_tickers(symbols):
        return SimpleNamespace(
            tickers={
                "PFE": FakeChartTicker({"regularMarketPrice": 100.0}),
                "MSFT": FakeChartTicker({}),
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


def test_quotes_skips_symbol_whose_fetch_raises(monkeypatch):
    """A single symbol's live chart fetch raising must not prevent the other
    symbols' quotes from being returned (#8094)."""

    boom = FakeChartTicker(error=RuntimeError("rate limited"))
    ok = FakeChartTicker({"regularMarketPrice": 100.0, "shortName": "OK Inc", "currency": "USD"})

    def fake_tickers(symbols):
        return SimpleNamespace(tickers={"BOOM": boom, "PFE": ok})

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", fake_tickers)
    monkeypatch.setattr(quotes_module.config, "offline_mode", False)
    client = _make_client()

    resp = client.get("/api/quotes?symbols=BOOM,PFE")
    assert resp.status_code == 200
    data = resp.json()
    assert [item["symbol"] for item in data] == ["PFE"]


def test_quotes_returns_502_when_every_symbol_fails(monkeypatch):
    """If every requested symbol's live fetch raises, surface a
    structured 502 rather than a misleadingly successful empty list."""

    def fake_tickers(symbols):
        return SimpleNamespace(tickers={"BOOM": FakeChartTicker(error=RuntimeError("boom"))})

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


def test_quotes_maps_app_exchange_suffixes_to_yahoo(monkeypatch):
    """``ADBE.N``/``UNH.US`` are fetched as Yahoo's bare ``ADBE``/``UNH`` but
    reported under the symbol the caller asked for; unmapped suffixes such as
    ``IWDA.AS`` are passed through unchanged."""

    requested = []

    def fake_tickers(symbols):
        requested.append(symbols)
        return SimpleNamespace(
            tickers={
                "ADBE": FakeChartTicker({"regularMarketPrice": 400.0}),
                "UNH": FakeChartTicker({"regularMarketPrice": 500.0}),
                "IWDA.AS": FakeChartTicker({"regularMarketPrice": 90.0}),
            }
        )

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", fake_tickers)
    monkeypatch.setattr(quotes_module.config, "offline_mode", False)
    client = _make_client()

    resp = client.get("/api/quotes?symbols=ADBE.N,unh.US,IWDA.AS")
    assert resp.status_code == 200
    assert requested == ["ADBE UNH IWDA.AS"]
    assert [item["symbol"] for item in resp.json()] == ["ADBE.N", "UNH.US", "IWDA.AS"]


def test_quotes_logs_and_skips_symbol_missing_from_provider(monkeypatch, caplog):
    """A symbol missing from ``Tickers.tickers`` is logged, not silently dropped (#8101)."""

    def fake_tickers(symbols):
        return SimpleNamespace(tickers={"PFE": FakeChartTicker({"regularMarketPrice": 100.0})})

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", fake_tickers)
    monkeypatch.setattr(quotes_module.config, "offline_mode", False)
    client = _make_client()

    with caplog.at_level("WARNING", logger=quotes_module.logger.name):
        resp = client.get("/api/quotes?symbols=GONE,PFE")

    assert resp.status_code == 200
    assert [item["symbol"] for item in resp.json()] == ["PFE"]
    warnings = [r.getMessage() for r in caplog.records if r.name == quotes_module.logger.name]
    assert warnings == ["No yfinance ticker returned for GONE, skipping"]


def test_quotes_logs_each_partial_fetch_failure(monkeypatch, caplog):
    """Partial failures keep the list shape but each failed symbol is logged at WARNING (#8097)."""

    def fake_tickers(symbols):
        return SimpleNamespace(
            tickers={
                "BOOM": FakeChartTicker(error=RuntimeError("rate limited")),
                "PFE": FakeChartTicker({"regularMarketPrice": 100.0}),
            }
        )

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", fake_tickers)
    monkeypatch.setattr(quotes_module.config, "offline_mode", False)
    client = _make_client()

    with caplog.at_level("WARNING", logger=quotes_module.logger.name):
        resp = client.get("/api/quotes?symbols=BOOM,PFE")

    assert resp.status_code == 200
    assert [item["symbol"] for item in resp.json()] == ["PFE"]
    records = [r for r in caplog.records if r.name == quotes_module.logger.name]
    assert [r.levelname for r in records] == ["WARNING"]
    assert "BOOM" in records[0].getMessage()


def test_quotes_all_fail_reports_only_failed_symbols(monkeypatch, caplog):
    """The all-fail 502 names the failed subset; a symbol missing from the
    provider response now counts as failed too (#8101, #8104)."""

    def fake_tickers(symbols):
        return SimpleNamespace(tickers={"BOOM": FakeChartTicker(error=RuntimeError("boom"))})

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", fake_tickers)
    monkeypatch.setattr(quotes_module.config, "offline_mode", False)
    client = _make_client()

    with caplog.at_level("ERROR", logger="backend.errors"):
        resp = client.get("/api/quotes?symbols=BOOM,GONE")

    assert resp.status_code == 502
    assert resp.json()["detail"] == "Upstream provider failure"
    record = caplog.records[-1]
    assert record.symbols == ["BOOM", "GONE"]
    assert set(record.provider_errors) == {"BOOM", "GONE"}
