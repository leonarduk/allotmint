"""Tests for start_date / end_date filtering on positions and timeseries routes.

Covers the six test categories from issue #2747 applied to the endpoints
updated in issue #3111:

  1. Default (no date params) – existing days-based behaviour unchanged.
  2. ``start_date`` only       – filtered from that date forward.
  3. ``end_date`` only         – filtered up to that date.
  4. Both ``start_date`` and ``end_date`` – exact explicit range.
  5. ``start_date`` > ``end_date`` – HTTP 422 rejected (meta) / HTTP 400 (instrument, portfolio).
  6. No data in range           – HTTP 404 returned.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
from fastapi.testclient import TestClient

from backend.config import config

# ── shared sample data ─────────────────────────────────────────────────────

_SAMPLE_DATES = pd.date_range("2024-01-01", periods=5, freq="D")

_SAMPLE_DF = pd.DataFrame(
    {
        "Date": _SAMPLE_DATES,
        "Open": [1.0] * 5,
        "High": [2.0] * 5,
        "Low": [0.5] * 5,
        "Close": [1.5] * 5,
        "Volume": [100] * 5,
        "Ticker": ["ABC"] * 5,
        "Source": ["test"] * 5,
    }
)

_EMPTY_DF = pd.DataFrame(
    columns=["Date", "Open", "High", "Low", "Close", "Volume", "Ticker", "Source"]
)


# ── /timeseries/meta ───────────────────────────────────────────────────────


def _meta_client(monkeypatch, df, captured: dict | None = None):
    """Return a TestClient wired to return *df* from load_meta_timeseries_range."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)

    import backend.routes.timeseries_meta as ts_meta

    def fake_load(ticker, exchange, start_date, end_date):
        if captured is not None:
            captured["start"] = start_date
            captured["end"] = end_date
        return df.copy()

    monkeypatch.setattr(ts_meta, "load_meta_timeseries_range", fake_load)
    monkeypatch.setattr(
        ts_meta.instrument_api,
        "_resolve_full_ticker",
        lambda t, latest: ("ABC", "L"),
    )

    from backend.app import create_app

    return TestClient(create_app())


def test_meta_default_no_date_params(monkeypatch):
    """Category 1: no date params – uses days default, returns data."""
    cap: dict = {}
    client = _meta_client(monkeypatch, _SAMPLE_DF, cap)

    resp = client.get("/timeseries/meta?ticker=ABC.L&format=json")

    assert resp.status_code == 200
    assert cap["start"] < cap["end"]


def test_meta_start_date_only(monkeypatch):
    """Category 2: start_date only overrides the lower bound."""
    cap: dict = {}
    client = _meta_client(monkeypatch, _SAMPLE_DF, cap)

    resp = client.get("/timeseries/meta?ticker=ABC.L&format=json&start_date=2024-01-03")

    assert resp.status_code == 200
    assert cap["start"] == dt.date(2024, 1, 3)


def test_meta_end_date_only(monkeypatch):
    """Category 3: end_date only overrides the upper bound.

    We pick an end_date that is within the default 365-day start window so the
    resulting range is valid (start <= end).
    """
    cap: dict = {}
    client = _meta_client(monkeypatch, _SAMPLE_DF, cap)
    # Use a date well within the last 365 days so start (today-365) stays before end.
    end = dt.date.today() - dt.timedelta(days=30)

    resp = client.get(f"/timeseries/meta?ticker=ABC.L&format=json&end_date={end}")

    assert resp.status_code == 200
    assert cap["end"] == end


def test_meta_both_dates(monkeypatch):
    """Category 4: both start_date and end_date override the window."""
    cap: dict = {}
    client = _meta_client(monkeypatch, _SAMPLE_DF, cap)

    resp = client.get(
        "/timeseries/meta?ticker=ABC.L&format=json"
        "&start_date=2024-01-02&end_date=2024-01-04"
    )

    assert resp.status_code == 200
    assert cap["start"] == dt.date(2024, 1, 2)
    assert cap["end"] == dt.date(2024, 1, 4)


def test_meta_start_after_end_is_422(monkeypatch):
    """Category 5: start_date after end_date returns HTTP 422.

    /timeseries/meta uses 422 (FastAPI's parameter-validation convention,
    issue #2747 AC) rather than 400.
    """
    client = _meta_client(monkeypatch, _SAMPLE_DF)

    resp = client.get(
        "/timeseries/meta?ticker=ABC.L"
        "&start_date=2024-06-01&end_date=2024-01-01"
    )

    assert resp.status_code == 422
    assert "start_date" in resp.text.lower()


def test_meta_no_data_in_range_is_404(monkeypatch):
    """Category 6: valid range but no data → HTTP 404."""
    client = _meta_client(monkeypatch, _EMPTY_DF)

    resp = client.get(
        "/timeseries/meta?ticker=ABC.L"
        "&start_date=2020-01-01&end_date=2020-12-31"
    )

    assert resp.status_code == 404


# ── /instrument/ ───────────────────────────────────────────────────────────


def _instrument_client(monkeypatch, df, captured: dict | None = None):
    """Return a TestClient wired to return *df* from load_meta_timeseries_range."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)

    import backend.routes.instrument as instr

    def fake_load(ticker, exchange, start_date, end_date):
        if captured is not None:
            captured["start_date"] = start_date
            captured["end_date"] = end_date
        return df.copy()

    monkeypatch.setattr(instr, "load_meta_timeseries_range", fake_load)
    monkeypatch.setattr(instr, "get_security_meta", lambda _t: {"name": "Test", "currency": "GBP"})
    monkeypatch.setattr(instr, "list_portfolios", lambda: [])
    monkeypatch.setattr(instr, "get_scaling_override", lambda *a, **k: 1.0)

    from backend.app import create_app

    return TestClient(create_app())


def test_instrument_default_no_date_params(monkeypatch):
    """Category 1: no date params – uses days default, returns data."""
    cap: dict = {}
    client = _instrument_client(monkeypatch, _SAMPLE_DF, cap)

    resp = client.get("/instrument?ticker=ABC.L&format=json")

    assert resp.status_code == 200
    assert cap["start_date"] < cap["end_date"]


def test_instrument_start_date_only(monkeypatch):
    """Category 2: start_date only overrides the lower bound."""
    cap: dict = {}
    client = _instrument_client(monkeypatch, _SAMPLE_DF, cap)

    resp = client.get("/instrument?ticker=ABC.L&format=json&start_date=2024-01-03")

    assert resp.status_code == 200
    assert cap["start_date"] == dt.date(2024, 1, 3)


def test_instrument_end_date_only(monkeypatch):
    """Category 3: end_date only overrides the upper bound.

    We pick an end_date that is within the default 365-day start window so the
    resulting range is valid (start <= end).
    """
    cap: dict = {}
    client = _instrument_client(monkeypatch, _SAMPLE_DF, cap)
    # Use a date well within the last 365 days so start (today-365) stays before end.
    end = dt.date.today() - dt.timedelta(days=30)

    resp = client.get(f"/instrument?ticker=ABC.L&format=json&end_date={end}")

    assert resp.status_code == 200
    assert cap["end_date"] == end


def test_instrument_both_dates(monkeypatch):
    """Category 4: both start_date and end_date."""
    cap: dict = {}
    client = _instrument_client(monkeypatch, _SAMPLE_DF, cap)

    resp = client.get(
        "/instrument?ticker=ABC.L&format=json"
        "&start_date=2024-01-02&end_date=2024-01-04"
    )

    assert resp.status_code == 200
    assert cap["start_date"] == dt.date(2024, 1, 2)
    assert cap["end_date"] == dt.date(2024, 1, 4)


def test_instrument_start_after_end_is_400(monkeypatch):
    """Category 5: start_date after end_date returns HTTP 400."""
    client = _instrument_client(monkeypatch, _SAMPLE_DF)

    resp = client.get(
        "/instrument?ticker=ABC.L"
        "&start_date=2024-06-01&end_date=2024-01-01"
    )

    assert resp.status_code == 400
    assert "start_date" in resp.text.lower()


def test_instrument_no_data_in_range_is_404(monkeypatch):
    """Category 6: valid range but empty data → HTTP 404 (json format)."""
    client = _instrument_client(monkeypatch, _EMPTY_DF)

    resp = client.get(
        "/instrument?ticker=ABC.L&format=json"
        "&start_date=2020-01-01&end_date=2020-12-31"
    )

    assert resp.status_code == 404


# ── /portfolio-group/{slug}/instrument/{ticker} ────────────────────────────


def _portfolio_instrument_client(monkeypatch, prices_list, captured: dict | None = None):
    """Return a TestClient wired to return *prices_list* from timeseries_for_ticker."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)

    import backend.common.instrument_api as iapi
    import backend.routes.portfolio as pf

    def fake_timeseries(ticker, days=365, start_date=None, end_date=None):
        if captured is not None:
            captured["start_date"] = start_date
            captured["end_date"] = end_date
        return {"prices": prices_list, "mini": {}}

    def fake_positions(slug, ticker):
        return [{"owner": "demo", "units": 10}]

    monkeypatch.setattr(iapi, "timeseries_for_ticker", fake_timeseries)
    monkeypatch.setattr(iapi, "positions_for_ticker", fake_positions)
    monkeypatch.setattr(pf, "instrument_api", iapi)

    from backend.app import create_app

    return TestClient(create_app())


_PRICES = [{"date": "2024-01-01", "close": 1.5, "close_gbp": 1.5}]


def test_portfolio_instrument_default_no_date_params(monkeypatch):
    """Category 1: no date params – uses days default."""
    cap: dict = {}
    client = _portfolio_instrument_client(monkeypatch, _PRICES, cap)

    resp = client.get("/portfolio-group/demo/instrument/VWRL.L")

    assert resp.status_code == 200
    assert cap["start_date"] is None
    assert cap["end_date"] is None


def test_portfolio_instrument_start_date_only(monkeypatch):
    """Category 2: start_date passed through to timeseries_for_ticker."""
    cap: dict = {}
    client = _portfolio_instrument_client(monkeypatch, _PRICES, cap)

    resp = client.get(
        "/portfolio-group/demo/instrument/VWRL.L?start_date=2024-01-03"
    )

    assert resp.status_code == 200
    assert cap["start_date"] == dt.date(2024, 1, 3)


def test_portfolio_instrument_end_date_only(monkeypatch):
    """Category 3: end_date passed through to timeseries_for_ticker.

    We pick an end_date within the last 365 days so the computed start
    (today - 365) remains before end — matching the pattern used in
    test_meta_end_date_only and test_instrument_end_date_only.
    A date more than 365 days in the past would cause resolve_date_range
    to compute start > end and return HTTP 400, which is correct behaviour
    but not what Category 3 is testing.
    """
    cap: dict = {}
    client = _portfolio_instrument_client(monkeypatch, _PRICES, cap)
    # Use a date well within the last 365 days so start (today-365) stays before end.
    end = dt.date.today() - dt.timedelta(days=30)

    resp = client.get(
        f"/portfolio-group/demo/instrument/VWRL.L?end_date={end}"
    )

    assert resp.status_code == 200
    assert cap["end_date"] == end


def test_portfolio_instrument_both_dates(monkeypatch):
    """Category 4: both start_date and end_date passed through."""
    cap: dict = {}
    client = _portfolio_instrument_client(monkeypatch, _PRICES, cap)

    resp = client.get(
        "/portfolio-group/demo/instrument/VWRL.L"
        "?start_date=2024-01-02&end_date=2024-01-04"
    )

    assert resp.status_code == 200
    assert cap["start_date"] == dt.date(2024, 1, 2)
    assert cap["end_date"] == dt.date(2024, 1, 4)


def test_portfolio_instrument_start_after_end_is_400(monkeypatch):
    """Category 5: start_date after end_date returns HTTP 400."""
    client = _portfolio_instrument_client(monkeypatch, _PRICES)

    resp = client.get(
        "/portfolio-group/demo/instrument/VWRL.L"
        "?start_date=2024-06-01&end_date=2024-01-01"
    )

    assert resp.status_code == 400
    assert "start_date" in resp.text.lower()


def test_portfolio_instrument_no_data_in_range_is_404(monkeypatch):
    """Category 6: no data and no positions → HTTP 404."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)

    import backend.common.instrument_api as iapi
    import backend.routes.portfolio as pf

    def fake_timeseries(ticker, days=365, start_date=None, end_date=None):
        return {"prices": [], "mini": {}}

    def fake_positions(slug, ticker):
        return []

    monkeypatch.setattr(iapi, "timeseries_for_ticker", fake_timeseries)
    monkeypatch.setattr(iapi, "positions_for_ticker", fake_positions)
    monkeypatch.setattr(pf, "instrument_api", iapi)

    from backend.app import create_app

    client = TestClient(create_app())
    resp = client.get(
        "/portfolio-group/demo/instrument/VWRL.L"
        "?start_date=2020-01-01&end_date=2020-12-31"
    )

    assert resp.status_code == 404
