import datetime as dt
from typing import Dict

import pandas as pd
import pytest

from backend.common import holding_utils
import backend.common.portfolio_utils as portfolio_utils


def test_close_column_selection():
    df = pd.DataFrame({"CLOSE_GBP": [1], "Close": [2], "Adj Close": [3]})
    assert holding_utils._close_column(df) == "CLOSE_GBP"
    assert holding_utils._close_column(pd.DataFrame({"Close": [1]})) == "Close"
    assert holding_utils._close_column(pd.DataFrame({"Adj Close": [1]})) == "Adj Close"
    assert holding_utils._close_column(pd.DataFrame({"adj_close": [1]})) == "adj_close"
    assert holding_utils._close_column(pd.DataFrame({"Other": [1]})) is None


def test_derived_cost_basis_close_px_caches_and_window(monkeypatch):
    calls = []

    def fake_load(ticker, exchange, start_date, end_date):
        calls.append((start_date, end_date))
        return pd.DataFrame({"Date": [start_date], "Close": [100.0]})

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_load)
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *a, **k: 0.5)

    acq = dt.date(2024, 1, 8)  # Monday
    cache: Dict[str, float] = {}
    px1 = holding_utils._derived_cost_basis_close_px("ABC", "L", acq, cache)
    px2 = holding_utils._derived_cost_basis_close_px("ABC", "L", acq, cache)

    assert px1 == 50.0
    assert px2 == 50.0
    assert len(calls) == 1
    assert calls[0][0] == dt.date(2024, 1, 5)  # start_date (Friday)
    assert calls[0][1] == dt.date(2024, 1, 10)  # end_date (Wednesday)


def test_load_latest_prices_resolution_scaling_and_missing(monkeypatch):
    def fake_resolve(full, result):
        return ("ABC", "L") if full == "ABC" else None

    def fake_load(ticker, exchange, start_date, end_date):
        if ticker == "ABC":
            return pd.DataFrame({"Date": [end_date], "Close": [10.0], "Close_gbp": [20.0]})
        return pd.DataFrame({"Date": [end_date], "Open": [1.0]})

    from backend.common import instrument_api

    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", fake_resolve)
    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_load)
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda t, e, r: 0.5 if t == "ABC" else 1.0)

    prices = holding_utils.load_latest_prices(["ABC", "XYZ"])
    assert prices == {"ABC.L": 10.0}


def test_load_latest_prices_handles_malformed(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise ValueError("bad data")

    from backend.common import instrument_api

    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda f, r: ("ABC", "L"))
    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", boom)

    with caplog.at_level("WARNING"):
        prices = holding_utils.load_latest_prices(["ABC"])
    assert prices == {}
    assert "latest price fetch failed" in caplog.text


def test_load_live_prices_with_fx(monkeypatch):
    ts = int(dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc).timestamp())

    class Resp:
        def json(self):
            return {
                "quoteResponse": {
                    "result": [
                        {"symbol": "ABC.L", "regularMarketPrice": 2.0, "regularMarketTime": ts},
                        {"symbol": "XYZ", "regularMarketPrice": 1.0, "regularMarketTime": ts},
                    ]
                }
            }

    monkeypatch.setattr(holding_utils.requests, "get", lambda url, timeout: Resp())
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda t, e, r: 0.5 if t == "ABC" else 1.0)
    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda s: {"currency": "GBP"} if s == "ABC.L" else {"currency": "USD"})
    monkeypatch.setattr(portfolio_utils, "_fx_to_base", lambda f, t, cache: 0.8)

    prices = holding_utils.load_live_prices(["ABC.L", "XYZ"])
    assert prices["ABC.L"]["price"] == 1.0
    assert prices["XYZ"]["price"] == pytest.approx(0.8)
    assert isinstance(prices["ABC.L"]["timestamp"], dt.datetime)
