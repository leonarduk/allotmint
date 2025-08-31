import datetime as dt

import pandas as pd
import pytest

from backend.common import holding_utils, portfolio_utils


def test_aggregate_with_mixed_holdings(monkeypatch):
    today = dt.date(2024, 1, 10)

    def fake_get_price_for_date_scaled(ticker, exchange, d, field="Close_gbp"):
        prices = {"AAA": 12.0, "CCC": 8.0}
        if ticker not in prices:
            raise AssertionError("price lookup should not occur for zero-unit holdings")
        return prices[ticker], "Feed"

    def fake_derived_cost_basis_close_px(ticker, exchange, acq, cache):
        prices = {"AAA": 10.0, "CCC": 7.0}
        if ticker not in prices:
            raise AssertionError("cost basis lookup should not occur for zero-unit holdings")
        return prices[ticker]

    monkeypatch.setattr(holding_utils, "_get_price_for_date_scaled", fake_get_price_for_date_scaled)
    monkeypatch.setattr(holding_utils, "_derived_cost_basis_close_px", fake_derived_cost_basis_close_px)

    holdings = [
        {"ticker": "AAA.L", "units": 10, "cost_basis_gbp": 100},
        {"ticker": "BBB.L", "units": 0},  # watchlist only
        {"ticker": "CCC.L", "units": 5},  # synthetic, derive cost basis
    ]
    price_cache = {}
    enriched = [holding_utils.enrich_holding(h, today, price_cache) for h in holdings]

    snapshot = {
        "AAA.L": {"last_price": 12.0, "last_price_date": "2024-01-09"},
        "BBB.L": {"last_price": 20.0, "last_price_date": "2024-01-09"},
        "CCC.L": {"last_price": 8.0, "last_price_date": "2024-01-09"},
    }
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", snapshot, raising=False)

    portfolio = {"accounts": [{"holdings": enriched}]}
    rows = {r["ticker"]: r for r in portfolio_utils.aggregate_by_ticker(portfolio)}

    assert rows["AAA.L"]["units"] == 10
    assert rows["AAA.L"]["market_value_gbp"] == 120.0
    assert rows["AAA.L"]["cost_gbp"] == 100.0

    assert rows["BBB.L"]["units"] == 0
    assert rows["BBB.L"]["market_value_gbp"] == 0.0

    assert rows["CCC.L"]["units"] == 5
    assert rows["CCC.L"]["cost_gbp"] == 35.0  # 5 * derived 7.0
    assert rows["CCC.L"]["market_value_gbp"] == 40.0


def test_performance_with_synthetic_holdings(monkeypatch):
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "AAA.L", "units": 10},
                    {"ticker": "BBB.L", "units": 0},
                    {"ticker": "CCC.L", "units": 5},
                ]
            }
        ]
    }

    monkeypatch.setattr(portfolio_utils.portfolio_mod, "build_owner_portfolio", lambda owner: portfolio)

    def fake_load_meta_timeseries(ticker, exchange, days):
        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        prices = {
            "AAA": [10, 11, 12],
            "CCC": [20, 21, 22],
        }
        return pd.DataFrame({"Date": dates, "Close": prices.get(ticker, [0, 0, 0])})

    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries)
    perf = portfolio_utils.compute_owner_performance("virtual", days=3)
    history = perf["history"] if isinstance(perf, dict) else perf

    assert len(history) == 3
    assert history[0]["value"] == 200  # 10*10 + 5*20
    assert history[-1]["value"] == 230  # 10*12 + 5*22
    assert history[-1]["cumulative_return"] == pytest.approx(0.15, rel=1e-3)
