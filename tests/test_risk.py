from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from backend.common import risk


def test_compute_sharpe_ratio(monkeypatch):
    data = [
        {"date": "2024-01-01", "value": 100, "daily_return": 0.01},
        {"date": "2024-01-02", "value": 101, "daily_return": 0.02},
        {"date": "2024-01-03", "value": 100, "daily_return": -0.01},
    ]
    monkeypatch.setattr(
        risk.portfolio_utils,
        "compute_owner_performance",
        lambda owner, days=3, include_cash=True: data,
    )
    monkeypatch.setattr(risk.config, "risk_free_rate", 0.01)
    rf = 0.01
    trading_days = 252
    returns = np.array([0.01, 0.02, -0.01])
    excess = returns - rf / trading_days
    expected = float(
        np.round((excess.mean() / excess.std(ddof=1)) * np.sqrt(trading_days), 4)
    )
    assert risk.compute_sharpe_ratio("steve", days=3) == expected


def test_compute_sharpe_ratio_insufficient(monkeypatch):
    monkeypatch.setattr(
        risk.portfolio_utils,
        "compute_owner_performance",
        lambda owner, days=3, include_cash=True: [],
    )
    assert risk.compute_sharpe_ratio("steve", days=3) is None


@patch("backend.common.portfolio_utils.compute_owner_performance", return_value=[])
def test_compute_portfolio_var_accepts_percentage(mock_perf):
    """compute_portfolio_var should accept confidence as a percentage."""

    result = risk.compute_portfolio_var("alex", confidence=95)

    # Confidence should be converted to the fractional form internally
    assert result["confidence"] == 0.95


@pytest.mark.parametrize(
    "include_cash, expected",
    [
        (
            True,
            [
                {"ticker": "CASH.GBP", "contribution": 1000.0},
                {"ticker": "VOD.L", "contribution": 150.0},
                {"ticker": "AAPL.US", "contribution": 15.0},
            ],
        ),
        (
            False,
            [
                {"ticker": "VOD.L", "contribution": 150.0},
                {"ticker": "AAPL.US", "contribution": 15.0},
            ],
        ),
    ],
)
def test_compute_portfolio_var_breakdown_deterministic(monkeypatch, include_cash, expected):
    holdings = [
        {"ticker": "CASH.GBP", "market_value_gbp": 2000.0, "currency": "GBP"},
        {
            "ticker": "VOD.L",
            "market_value_gbp": None,
            "currency": "GBP",
            "units": 100,
        },
        {"ticker": "AAPL.US", "market_value_gbp": 1500.0, "currency": "USD"},
    ]

    monkeypatch.setattr(
        risk.portfolio_mod,
        "build_owner_portfolio",
        lambda owner: {"owner": owner},
    )
    monkeypatch.setattr(
        risk.portfolio_utils,
        "aggregate_by_ticker",
        lambda portfolio: holdings,
    )

    closes_map = {
        "CASH.GBP": [1.0, 1.0, 1.0],
        "VOD.L": [9.0, 10.0],
        "AAPL.US": [198.0, 200.0],
    }
    var_map = {"CASH.GBP": 0.5, "VOD.L": 1.5, "AAPL.US": 2.0}

    def fake_load_meta_timeseries(symbol, exchange, days):
        key = f"{symbol}.{exchange}"
        df = pd.DataFrame({"Close": closes_map[key]})
        df.attrs["ticker"] = key
        return df

    def fake_compute_var(ts, confidence):
        return var_map[ts.attrs["ticker"]]

    monkeypatch.setattr(
        risk.portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries
    )
    monkeypatch.setattr(risk.portfolio_utils, "compute_var", fake_compute_var)

    result = risk.compute_portfolio_var_breakdown(
        "owner", days=10, confidence=0.95, include_cash=include_cash
    )

    assert result == expected


@pytest.mark.parametrize("confidence", [0, 101])
def test_compute_portfolio_var_breakdown_invalid_confidence(confidence):
    with pytest.raises(ValueError):
        risk.compute_portfolio_var_breakdown("owner", confidence=confidence)


def test_compute_portfolio_var_breakdown_invalid_days():
    with pytest.raises(ValueError):
        risk.compute_portfolio_var_breakdown("owner", days=0)
