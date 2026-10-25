import logging

import pandas as pd
import pytest

from backend.common import portfolio as portfolio_mod
from backend.common import portfolio_utils


@pytest.fixture
def price_data():
    idx = pd.date_range("2024-01-01", periods=5, freq="D").date
    return {
        "AAA": pd.DataFrame({"Date": idx, "Close": [100, 120, 110, 130, 115]}),
        "BADZERO": pd.DataFrame({"Date": idx, "Close": [100, 0, 95, 105, 100]}),
        "FLAG": pd.DataFrame({"Date": idx, "Close": [50, 40, 30, 20, 10]}),
    }


@pytest.fixture
def mock_env(monkeypatch, price_data):
    owners = {
        "normal": [{"ticker": "AAA", "exchange": "L", "units": 1}],
        "mixed": [
            {"ticker": "AAA", "exchange": "L", "units": 1},
            {"ticker": "BADZERO", "exchange": "L", "units": 1},
            {"ticker": "FLAG", "exchange": "L", "units": 1},
        ],
    }

    def fake_build_owner_portfolio(owner, accounts_root=None, pricing_date=None):
        return {"accounts": [{"holdings": owners[owner]}]}

    monkeypatch.setattr(portfolio_mod, "build_owner_portfolio", fake_build_owner_portfolio)

    def fake_resolve(ticker, latest):
        return ticker.split(".")[0], "L"

    monkeypatch.setattr("backend.common.instrument_api._resolve_full_ticker", fake_resolve)

    calls = []

    def fake_load_meta_timeseries(ticker, exchange, days):
        calls.append((ticker, exchange))
        return price_data.get(ticker, pd.DataFrame())

    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries)

    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {"FLAG.L": {"flagged": True}})

    return calls


def test_compute_max_drawdown_normal_series(mock_env):
    val = portfolio_utils.compute_max_drawdown("normal", days=5)
    assert val == pytest.approx(-0.11538, rel=1e-4)
    assert mock_env == [("AAA", "L")]


def test_compute_max_drawdown_ignores_flagged(mock_env):
    val = portfolio_utils.compute_max_drawdown("mixed", days=5)
    assert val == pytest.approx(-0.4, rel=1e-4)
    assert ("FLAG", "L") not in mock_env


def test_compute_max_drawdown_forward_fills_short_price_gaps(monkeypatch):
    idx = pd.date_range("2024-01-01", periods=4, freq="D").date
    series_by_ticker = {
        "STEADY": pd.DataFrame({"Date": idx, "Close": [100, 100, 100, 100]}),
        "GAPPY": pd.DataFrame(
            {
                "Date": [idx[0], idx[1], idx[3]],
                "Close": [400, 420, 430],
            }
        ),
    }

    def fake_build_owner_portfolio(owner, accounts_root=None, pricing_date=None):
        return {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "STEADY", "exchange": "L", "units": 1},
                        {"ticker": "GAPPY", "exchange": "L", "units": 1},
                    ]
                }
            ]
        }

    monkeypatch.setattr(portfolio_mod, "build_owner_portfolio", fake_build_owner_portfolio)
    monkeypatch.setattr(
        "backend.common.instrument_api._resolve_full_ticker",
        lambda ticker, latest: (ticker.split(".")[0], "L"),
    )
    monkeypatch.setattr(
        portfolio_utils,
        "load_meta_timeseries",
        lambda ticker, exchange, days: series_by_ticker.get(ticker, pd.DataFrame()),
    )
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})

    reconstructed = portfolio_utils._portfolio_value_series("gap-owner", days=10)
    max_drawdown = portfolio_utils.compute_max_drawdown("gap-owner", days=10)

    assert reconstructed.loc[idx[2]] == pytest.approx(520.0)
    assert max_drawdown == pytest.approx(0.0)


def _patch_gap_owner(monkeypatch, series_by_ticker):
    def fake_build_owner_portfolio(owner, accounts_root=None, pricing_date=None):
        holdings = [{"ticker": ticker, "exchange": "L", "units": 1} for ticker in series_by_ticker]
        return {"accounts": [{"holdings": holdings}]}

    monkeypatch.setattr(portfolio_mod, "build_owner_portfolio", fake_build_owner_portfolio)
    monkeypatch.setattr(
        "backend.common.instrument_api._resolve_full_ticker",
        lambda ticker, latest: (ticker.split(".")[0], "L"),
    )
    monkeypatch.setattr(
        portfolio_utils,
        "load_meta_timeseries",
        lambda ticker, exchange, days: series_by_ticker.get(ticker, pd.DataFrame()),
    )
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})


def test_portfolio_value_series_carries_long_price_gaps_forward(monkeypatch):
    """A holding with no close for days (suspended, stale feed) is still owned: its last value carries (#9696)."""
    idx = pd.date_range("2024-01-01", periods=10, freq="D").date
    _patch_gap_owner(
        monkeypatch,
        {
            "STEADY": pd.DataFrame({"Date": idx, "Close": [100] * len(idx)}),
            "GAPPY": pd.DataFrame({"Date": [idx[0], idx[1], idx[8], idx[9]], "Close": [400, 420, 410, 415]}),
        },
    )

    reconstructed = portfolio_utils._portfolio_value_series("gap-owner", days=10)

    assert reconstructed.loc[idx[5]] == pytest.approx(520.0)
    assert reconstructed.loc[idx[7]] == pytest.approx(520.0)


def test_owner_performance_and_max_drawdown_agree_across_a_long_price_gap(monkeypatch):
    """Both valuation paths carry a 10-row price gap the same way, so max drawdown matches exactly (#9696)."""
    idx = pd.bdate_range("2024-01-01", periods=16).date
    steady = [100.0, 104.0, 98.0, 101.0, 97.0, 99.0, 103.0, 96.0, 100.0, 102.0, 95.0, 99.0, 101.0, 104.0, 97.0, 100.0]
    gap_dates = [idx[0], idx[1], idx[2], idx[13], idx[14], idx[15]]
    _patch_gap_owner(
        monkeypatch,
        {
            "STEADY": pd.DataFrame({"Date": idx, "Close": steady}),
            "GAPPY": pd.DataFrame({"Date": gap_dates, "Close": [400.0, 420.0, 410.0, 380.0, 390.0, 415.0]}),
        },
    )
    pricing_date = idx[-1]

    performance = portfolio_utils.compute_owner_performance("gap-owner", days=30, pricing_date=pricing_date)
    drawdown, breakdown = portfolio_utils.compute_max_drawdown(
        "gap-owner", days=30, include_breakdown=True, pricing_date=pricing_date
    )

    assert performance["max_drawdown"] == drawdown
    assert [row["value"] for row in performance["history"]] == [
        round(row["portfolio_value"], 2) for row in breakdown["series"]
    ]
    # Mid-gap the stale GAPPY close (410) is still in the total, not dropped after a few rows.
    assert breakdown["series"][9]["portfolio_value"] == pytest.approx(102.0 + 410.0)


def reconcile(owner, price_data):
    for tkr, df in price_data.items():
        bad = df[df["Close"] <= 0]
        if not bad.empty:
            d = bad.iloc[0]["Date"]
            logging.warning("Bad series for %s on %s", tkr, d)
    return portfolio_utils.compute_max_drawdown(owner, days=5)


def test_reconciliation_warns_bad_series(price_data, mock_env, caplog):
    with caplog.at_level("WARNING"):
        reconcile("mixed", price_data)
    assert any("BADZERO" in r.message and "2024-01-02" in r.message for r in caplog.records)
