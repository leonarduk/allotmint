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
        lambda owner, days=3, include_cash=True, **kwargs: data,
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
        lambda owner, days=3, include_cash=True, **kwargs: [],
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
                {"ticker": "PFE.US", "contribution": 15.0},
            ],
        ),
        (
            False,
            [
                {"ticker": "VOD.L", "contribution": 150.0},
                {"ticker": "PFE.US", "contribution": 15.0},
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
        {"ticker": "PFE.US", "market_value_gbp": 1500.0, "currency": "USD"},
    ]

    monkeypatch.setattr(
        risk.portfolio_mod,
        "build_owner_portfolio",
        lambda owner, *, pricing_date=None, **_: {"owner": owner},
    )
    monkeypatch.setattr(
        risk.portfolio_utils,
        "aggregate_by_ticker",
        lambda portfolio: holdings,
    )

    closes_map = {
        "CASH.GBP": [1.0, 1.0, 1.0],
        "VOD.L": [9.0, 10.0],
        "PFE.US": [198.0, 200.0],
    }
    var_map = {"CASH.GBP": 0.5, "VOD.L": 1.5, "PFE.US": 2.0}

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


def test_compute_portfolio_var_breakdown_accepts_percentage(monkeypatch):
    monkeypatch.setattr(
        risk.portfolio_mod,
        "build_owner_portfolio",
        lambda owner: {"owner": owner},
    )
    monkeypatch.setattr(risk.portfolio_utils, "aggregate_by_ticker", lambda portfolio: [])

    result = risk.compute_portfolio_var_breakdown("owner", confidence=95)

    assert result == []


def test_compute_portfolio_var_invalid_days():
    with pytest.raises(ValueError):
        risk.compute_portfolio_var("owner", days=0)


def test_compute_portfolio_var_invalid_confidence():
    with pytest.raises(ValueError):
        risk.compute_portfolio_var("owner", confidence=1.5)


def test_compute_portfolio_var_returns_none_when_no_history(monkeypatch):
    def fake_perf(owner, days=365, include_flagged=False, include_cash=True):
        return {"history": []}

    monkeypatch.setattr(
        risk.portfolio_utils,
        "compute_owner_performance",
        fake_perf,
    )

    result = risk.compute_portfolio_var("owner")

    assert result == {"window_days": 365, "confidence": 0.95, "1d": None, "10d": None}


def test_compute_portfolio_var_handles_empty_returns(monkeypatch):
    history = [
        {"value": 100.0, "daily_return": None},
        {"value": 101.0, "daily_return": float("nan")},
    ]

    def fake_perf(owner, days=365, include_flagged=False, include_cash=True):
        return history

    monkeypatch.setattr(
        risk.portfolio_utils,
        "compute_owner_performance",
        fake_perf,
    )

    result = risk.compute_portfolio_var("owner")

    assert result == {"window_days": 365, "confidence": 0.95, "1d": None, "10d": None}


def test_compute_portfolio_var_handles_nan_quantiles(monkeypatch):
    history = []
    for idx in range(11):
        daily_return = 1e308 if idx < 10 else -1e308
        history.append({"value": 100.0 + idx, "daily_return": daily_return})

    monkeypatch.setattr(
        risk.portfolio_utils,
        "compute_owner_performance",
        lambda owner, days=365, include_flagged=False, include_cash=True: {"history": history},
    )

    result = risk.compute_portfolio_var("owner", days=10)

    assert result["1d"] is None
    assert result["10d"] is None


def test_compute_portfolio_var_produces_values(monkeypatch):
    returns = [0.01, -0.015, 0.02, -0.005, 0.012, -0.01, 0.018, -0.007, 0.009, -0.012, 0.011]
    values = list(np.linspace(100, 110, num=len(returns) + 1))
    history = []
    for idx, ret in enumerate(returns, start=1):
        history.append(
            {
                "date": f"2024-01-{idx:02d}",
                "value": values[idx],
                "daily_return": ret,
            }
        )

    monkeypatch.setattr(
        risk.portfolio_utils,
        "compute_owner_performance",
        lambda owner, days=11, include_flagged=False, include_cash=True: {"history": history},
    )

    result = risk.compute_portfolio_var("owner", days=10, confidence=0.9)

    df = pd.DataFrame(history[-11:])
    returns_series = df["daily_return"].dropna()
    if len(returns_series) > 10:
        returns_series = returns_series.iloc[-10:]
    expected_1d = max(-(returns_series.quantile(0.1)), 0.0) * float(df["value"].iloc[-1])
    ten_day = returns_series.add(1).rolling(10).apply(np.prod) - 1
    expected_10d = max(-(ten_day.dropna().quantile(0.1)), 0.0) * float(df["value"].iloc[-1])

    assert result["window_days"] == 10
    assert result["confidence"] == 0.9
    assert result["1d"] == round(expected_1d, 2)
    assert result["10d"] == round(expected_10d, 2)


def test_compute_portfolio_var_handles_nan_quantiles(monkeypatch):
    history = [
        {"value": 100.0, "daily_return": 0.01},
        {"value": 101.0, "daily_return": -0.02},
    ]

    def fake_perf(owner, days=365, include_flagged=False, include_cash=True):
        return {"history": history}

    monkeypatch.setattr(risk.portfolio_utils, "compute_owner_performance", fake_perf)

    def always_nan(self, q):
        return float("nan")

    monkeypatch.setattr(pd.Series, "quantile", always_nan)

    result = risk.compute_portfolio_var("owner", days=1)

    assert result["1d"] is None
    assert result["10d"] is None


def test_compute_portfolio_var_breakdown_skip_conditions(monkeypatch):
    holdings = [
        {"ticker": None},
        {"ticker": "CASH.GBP"},
        {"ticker": "ABC.L"},
        {"ticker": "DEF.L"},
        {"ticker": "GHI.L"},
        {"ticker": "JKL.L"},
        {"ticker": "MNO.L", "market_value_gbp": 0.0, "currency": "USD"},
        {"ticker": "PQR.L", "market_value_gbp": 100.0},
    ]

    monkeypatch.setattr(risk.portfolio_mod, "build_owner_portfolio", lambda owner: {})
    monkeypatch.setattr(risk.portfolio_utils, "aggregate_by_ticker", lambda portfolio: holdings)

    def fake_load_meta_timeseries(symbol, exchange, days):
        key = f"{symbol}.{exchange}"
        if key == "ABC.L":
            return None
        if key == "DEF.L":
            return pd.DataFrame({})
        if key == "GHI.L":
            return pd.DataFrame({"Close": [float("nan")]})
        if key == "JKL.L":
            return pd.DataFrame({"Close": [0.0]})
        if key == "MNO.L":
            return pd.DataFrame({"Close": [1.0]})
        return pd.DataFrame({"Close": [10.0, 11.0]})

    def fake_compute_var(ts, confidence):
        if ts is None:
            return None
        return 5.0

    monkeypatch.setattr(risk.portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries)
    monkeypatch.setattr(risk.portfolio_utils, "compute_var", fake_compute_var)

    result = risk.compute_portfolio_var_breakdown("owner", include_cash=False)

    assert result == [
        {"ticker": "PQR.L", "contribution": pytest.approx(45.45, rel=1e-2)}
    ]


def test_compute_sharpe_ratio_invalid_days():
    with pytest.raises(ValueError):
        risk.compute_sharpe_ratio("owner", days=0)


def test_compute_sharpe_ratio_handles_dict_payload(monkeypatch):
    perf = {"history": [{"daily_return": 0.01}]}
    monkeypatch.setattr(risk.portfolio_utils, "compute_owner_performance", lambda owner, days=1: perf)

    assert risk.compute_sharpe_ratio("owner", days=1) is None


def test_compute_sharpe_ratio_returns_none_when_std_zero(monkeypatch):
    history = [
        {"daily_return": 0.01},
        {"daily_return": 0.01},
        {"daily_return": 0.01},
    ]
    monkeypatch.setattr(risk.portfolio_utils, "compute_owner_performance", lambda owner, days=3: history)
    monkeypatch.setattr(risk.config, "risk_free_rate", 0.0, raising=False)

    assert risk.compute_sharpe_ratio("owner", days=3) is None
