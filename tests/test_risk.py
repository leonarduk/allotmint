import pandas as pd
import pytest

from backend.common import risk


def test_compute_sortino_ratio(monkeypatch):
    perf = [
        {"date": "2024-01-01", "value": 100.0, "daily_return": None},
        {"date": "2024-01-02", "value": 101.0, "daily_return": 0.01},
        {"date": "2024-01-03", "value": 99.0, "daily_return": -0.02},
        {"date": "2024-01-04", "value": 100.5, "daily_return": 0.015},
        {"date": "2024-01-05", "value": 99.5, "daily_return": -0.01},
    ]

    monkeypatch.setattr(
        "backend.common.portfolio_utils.compute_owner_performance",
        lambda owner, days=365: perf,
    )

    ratio = risk.compute_sortino_ratio("alice")
    returns = pd.Series([0.01, -0.02, 0.015, -0.01])
    expected = returns.mean() / returns[returns < 0].std()
    assert ratio == pytest.approx(expected)
