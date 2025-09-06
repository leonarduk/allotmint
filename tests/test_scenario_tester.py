from datetime import date

import pandas as pd
import pytest
import backend.common.prices as prices
from backend.utils import scenario_tester as sc_tester


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
