import datetime as dt
from datetime import date
from types import SimpleNamespace

import backend.common.prices as prices
import pandas as pd
from backend.utils import scenario_tester as sc
from backend.utils.scenario_tester import apply_historical_event, apply_price_shock


def test_price_shock_uses_cached_price_for_missing_current_price(monkeypatch):
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": "ABC.L",
                        "units": 10,
                        "market_value_gbp": 0.0,
                    }
                ],
                "value_estimate_gbp": 0.0,
            }
        ],
        "total_value_estimate_gbp": 0.0,
    }

    monkeypatch.setattr(prices, "_price_cache", {"ABC.L": 5.0})

    shocked = sc_tester.apply_price_shock(portfolio, "ABC.L", 10)

    assert shocked["accounts"][0]["value_estimate_gbp"] > 0
    assert shocked["total_value_estimate_gbp"] > 0


def test_apply_historical_event_uses_proxy_for_missing(monkeypatch):
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "ABC.L", "market_value_gbp": 100},
                    {"ticker": "MISSING.L", "market_value_gbp": 100},
                ]
            }
        ],
        "total_value_estimate_gbp": 200,
    }

    event = SimpleNamespace(date=dt.date(2020, 1, 1), proxy="IDX.L")

    dates = [
        dt.date(2020, 1, 1),
        dt.date(2020, 1, 2),
        dt.date(2020, 1, 8),
        dt.date(2020, 1, 31),
        dt.date(2020, 3, 31),
        dt.date(2020, 12, 31),
    ]
    abc = pd.DataFrame({"Date": dates, "Close": [10, 11, 12, 15, 20, 30]})
    idx = pd.DataFrame({"Date": dates, "Close": [100, 110, 120, 150, 200, 300]})

    def fake_load(ticker, exchange, start_date, end_date):
        if ticker == "ABC":
            return abc
        if ticker == "IDX":
            return idx
        return pd.DataFrame()

    monkeypatch.setattr(sc, "load_meta_timeseries_range", fake_load)
    monkeypatch.setattr(sc, "get_scaling_override", lambda *a, **k: 1.0)
    monkeypatch.setattr(sc, "apply_scaling", lambda df, scale, scale_volume=False: df)

    result = apply_historical_event(portfolio, event)

    assert result["1d"]["total_value_gbp"] == 220.0
    assert result["1y"]["total_value_gbp"] == 600.0

def test_apply_historical_event_scales_portfolio():
    portfolio = {
        "accounts": [{"value_estimate_gbp": 100.0}],
        "total_value_estimate_gbp": 100.0,
    }

    shocked = apply_historical_event(portfolio, event_id="dummy", horizons=[1, 5])

    assert 1 in shocked and 5 in shocked
    assert shocked[1]["total_value_estimate_gbp"] < portfolio["total_value_estimate_gbp"]

def test_historical_event_falls_back_to_proxy(monkeypatch):
    portfolio = {"accounts": [{"holdings": [{"ticker": "AAA.L"}]}]}
    event = {
        "date": date(2020, 1, 1),
        "horizons": [5],
        "proxy_index": {"ticker": "SPY", "exchange": "N"},
    }

    df_proxy = pd.DataFrame(
        {"Close": [100.0, 110.0]},
        index=pd.to_datetime(["2020-01-01", "2020-01-06"]),
    )

    def fake_load(ticker, exchange, start_date, end_date):
        if ticker == "AAA":
            return pd.DataFrame()
        return df_proxy

    monkeypatch.setattr(sc_tester, "load_meta_timeseries_range", fake_load)

    returns = sc_tester.apply_historical_event(portfolio, event)
    assert returns["AAA.L"][5] == pytest.approx(0.1)


def test_historical_event_uses_proxy_when_data_incomplete(monkeypatch):
    portfolio = {"accounts": [{"holdings": [{"ticker": "AAA.L"}]}]}
    event = {
        "date": date(2020, 1, 1),
        "horizons": [5],
        "proxy_index": {"ticker": "SPY", "exchange": "N"},
    }

    df_partial = pd.DataFrame(
        {"Close": [100.0, 101.0]},
        index=pd.to_datetime(["2020-01-01", "2020-01-02"]),
    )
    df_proxy = pd.DataFrame(
        {"Close": [100.0, 110.0]},
        index=pd.to_datetime(["2020-01-01", "2020-01-06"]),
    )

    def fake_load(ticker, exchange, start_date, end_date):
        if ticker == "AAA":
            return df_partial
        return df_proxy

    monkeypatch.setattr(sc_tester, "load_meta_timeseries_range", fake_load)

    returns = sc_tester.apply_historical_event(portfolio, event)
    assert returns["AAA.L"][5] == pytest.approx(0.1)
