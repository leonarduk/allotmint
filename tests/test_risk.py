import numpy as np
import pytest
from unittest.mock import patch
from backend.common import risk


def test_compute_sharpe_ratio(monkeypatch):
    data = [
        {"date": "2024-01-01", "value": 100, "daily_return": 0.01},
        {"date": "2024-01-02", "value": 101, "daily_return": 0.02},
        {"date": "2024-01-03", "value": 100, "daily_return": -0.01},
    ]
    monkeypatch.setattr(risk.portfolio_utils, "compute_owner_performance", lambda owner, days=3: data)
    monkeypatch.setattr(risk.config, "risk_free_rate", 0.01)
    rf = 0.01
    trading_days = 252
    returns = np.array([0.01, 0.02, -0.01])
    excess = returns - rf / trading_days
    expected = float(np.round((excess.mean()/excess.std(ddof=1))*np.sqrt(trading_days), 4))
    assert risk.compute_sharpe_ratio("steve", days=3) == expected


def test_compute_sharpe_ratio_insufficient(monkeypatch):
    monkeypatch.setattr(risk.portfolio_utils, "compute_owner_performance", lambda owner, days=3: [])
    assert risk.compute_sharpe_ratio("steve", days=3) is None


def test_compute_sortino_ratio(monkeypatch):
    data = [
        {"date": "2024-01-01", "value": 100, "daily_return": 0.01},
        {"date": "2024-01-02", "value": 101, "daily_return": 0.02},
        {"date": "2024-01-03", "value": 99, "daily_return": -0.02},
        {"date": "2024-01-04", "value": 98, "daily_return": -0.01},
    ]
    monkeypatch.setattr(risk.portfolio_utils, "compute_owner_performance", lambda owner, days=4: data)
    monkeypatch.setattr(risk.config, "risk_free_rate", 0.01)
    rf = 0.01
    trading_days = 252
    returns = np.array([0.01, 0.02, -0.02, -0.01])
    excess = returns - rf / trading_days
    downside = excess[excess < 0]
    expected = float(np.round((excess.mean()/downside.std(ddof=1))*np.sqrt(trading_days), 4))
    assert risk.compute_sortino_ratio("steve", days=4) == expected


def test_compute_sortino_ratio_insufficient(monkeypatch):
    data = [
        {"date": "2024-01-01", "value": 100, "daily_return": 0.01},
        {"date": "2024-01-02", "value": 101, "daily_return": 0.02},
    ]
    monkeypatch.setattr(risk.portfolio_utils, "compute_owner_performance", lambda owner, days=2: data)
    assert risk.compute_sortino_ratio("steve", days=2) is None

@patch("backend.common.portfolio_utils.compute_owner_performance", return_value=[])
def test_compute_portfolio_var_accepts_percentage(mock_perf):
    """compute_portfolio_var should accept confidence as a percentage."""

    result = risk.compute_portfolio_var("alex", confidence=95)

    # Confidence should be converted to the fractional form internally
    assert result["confidence"] == 0.95
