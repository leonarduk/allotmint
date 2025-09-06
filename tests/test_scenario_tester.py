import datetime as dt
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

    shocked = apply_price_shock(portfolio, "ABC.L", 10)

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
