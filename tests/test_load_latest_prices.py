import datetime as dt

import pandas as pd
import pytest

from backend.common import holding_utils, refresh_progress


@pytest.mark.parametrize(
    "data,expected",
    [
        ({"Date": [1], "Close_gbp": [2.0], "Close": [1.0]}, 2.0),
        ({"Date": [1], "Close": [1.5]}, 1.5),
        ({"Date": [1], "close_gbp": [3.0]}, 3.0),
        ({"Date": [1], "close": [4.0]}, 4.0),
    ],
)
def test_load_latest_prices_selects_close_column(monkeypatch, data, expected):
    def fake_load_meta_timeseries_range(ticker, exchange, start_date, end_date):
        return pd.DataFrame(data)

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_load_meta_timeseries_range)
    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda *_: {"currency": "GBP"})

    prices = holding_utils.load_latest_prices(["ABC.L"])
    assert prices["ABC.L"] == expected


def test_load_latest_prices_applies_scaling(monkeypatch):
    df = pd.DataFrame({"Date": [1], "Close": [20.0]})

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", lambda *a, **k: df)
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *a, **k: 0.5)
    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda *_: {"currency": "GBP"})

    prices = holding_utils.load_latest_prices(["ABC.L"])
    assert prices["ABC.L"] == 10.0


def test_load_latest_prices_converts_native_close_to_gbp(monkeypatch):
    from backend.common import portfolio_utils

    df = pd.DataFrame({"Date": [1], "Close": [100.0]})
    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", lambda *a, **k: df)
    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda *_: {"currency": "USD"})
    monkeypatch.setattr(portfolio_utils, "_fx_to_base", lambda *_: 0.8)

    prices = holding_utils.load_latest_prices(["USDX.US"])

    assert prices["USDX.US"] == pytest.approx(80.0)


def test_load_latest_prices_handles_errors(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", boom)

    with caplog.at_level("WARNING"):
        prices = holding_utils.load_latest_prices(["ABC.L"])

    assert prices == {}
    assert "latest price fetch failed" in caplog.text


def test_load_latest_prices_names_unpriced_tickers(monkeypatch, caplog):
    """A ticker with no cached/fetched data is named in a warning, not just counted (#8599)."""

    def fake_range(ticker, exchange, start_date, end_date):
        if ticker == "GOOD":
            return pd.DataFrame({"Date": [1], "Close_gbp": [2.0]})
        return pd.DataFrame()

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_range)

    with caplog.at_level("WARNING", logger=holding_utils.logger.name):
        prices = holding_utils.load_latest_prices(["GOOD.L", "GONE.L"])

    assert prices == {"GOOD.L": 2.0}
    messages = [
        r.getMessage() for r in caplog.records if r.name == holding_utils.logger.name and r.levelname == "WARNING"
    ]
    assert messages == ["No latest price for 1 ticker(s): GONE.L"]


def test_load_latest_prices_reports_progress_when_opted_in(monkeypatch):
    df = pd.DataFrame({"Date": [1], "Close_gbp": [2.0]})
    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", lambda *a, **k: df)

    refresh_progress.start(2)
    try:
        holding_utils.load_latest_prices(["ABC.L", "DEF.L"], report_progress=True)
        snap = refresh_progress.snapshot()
    finally:
        refresh_progress.finish()

    assert snap["completed"] == 2
    assert snap["current_ticker"] == "DEF.L"


def test_load_latest_prices_ignores_progress_when_no_refresh_running(monkeypatch):
    df = pd.DataFrame({"Date": [1], "Close_gbp": [2.0]})
    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", lambda *a, **k: df)

    refresh_progress.finish()
    holding_utils.load_latest_prices(["ABC.L"], report_progress=True)

    assert refresh_progress.snapshot()["running"] is False


def test_load_latest_prices_does_not_report_progress_by_default(monkeypatch):
    """An unrelated caller (report_progress defaults to False) must never
    corrupt an in-flight refresh's progress with its own ticker list — the
    cross-caller contamination guarded against in refresh_progress.py."""
    df = pd.DataFrame({"Date": [1], "Close_gbp": [2.0]})
    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", lambda *a, **k: df)

    refresh_progress.start(5)
    try:
        refresh_progress.update("REAL.L", 1)
        # A different caller (e.g. instrument_api's own price map build)
        # runs concurrently with its own, unrelated ticker list — it must
        # not touch the tracked refresh's progress at all.
        holding_utils.load_latest_prices(["UNRELATED.L"])
        snap = refresh_progress.snapshot()
    finally:
        refresh_progress.finish()

    assert snap["completed"] == 1
    assert snap["current_ticker"] == "REAL.L"


def test_enrich_holding_uses_scaling_override(monkeypatch):
    def fake_load_meta_timeseries_range(ticker, exchange, start_date, end_date):
        return pd.DataFrame({"Date": [start_date], "Close": [2000.0]})

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_load_meta_timeseries_range)

    holding = {"ticker": "ADM.L", "units": 1, "cost_basis_gbp": 100}
    enriched = holding_utils.enrich_holding(holding, dt.date(2024, 1, 3), {})

    assert enriched["current_price_gbp"] == 200.0
    assert enriched["gain_pct"] == pytest.approx(100.0)
