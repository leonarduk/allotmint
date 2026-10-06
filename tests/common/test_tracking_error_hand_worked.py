"""Pin the tracking-error formula against a hand-worked example (#7816 AC #2).

Benchmark rises 0.5% every day. The portfolio alternates +1.5% / -0.5%, so the
daily active return (portfolio - benchmark) is exactly +1%, -1%, +1%, -1%.

    mean active return          = 0
    sample variance (ddof = 1)  = 4 * 0.01**2 / (4 - 1) = 0.0004 / 3
    daily std                   = sqrt(0.0004 / 3)       = 0.0115470...
    annualised (x sqrt(252))    = sqrt(0.0004 / 3 * 252) = sqrt(0.0336)
                                = 0.1833030...  (i.e. 18.33%, as a decimal)

A units or annualisation bug moves this away from 0.1833: percent units give
18.33, sqrt(365) gives 0.2206, a population std (ddof = 0) gives 0.1587, and
annualising variance instead of std (x 252) gives 0.0336.
"""

import math

import pandas as pd
import pytest

from backend.common import portfolio_utils

EXPECTED_DAILY_STD = math.sqrt(0.0004 / 3)
EXPECTED_TRACKING_ERROR = math.sqrt(0.0336)


@pytest.fixture
def hand_worked_series(monkeypatch: pytest.MonkeyPatch) -> None:
    dates = pd.bdate_range("2024-01-01", periods=5)

    bench = [100.0]
    for _ in range(4):
        bench.append(bench[-1] * 1.005)

    port = [100.0]
    for growth in (1.015, 0.995, 1.015, 0.995):
        port.append(port[-1] * growth)

    portfolio_series = pd.Series(port, index=dates.date)

    def fake_portfolio_value_series(name: str, days: int, *, group: bool = False, pricing_date=None, **_):
        return portfolio_series

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        return pd.DataFrame({"Date": dates, "Close": bench})

    monkeypatch.setattr(
        portfolio_utils,
        "_portfolio_return_series",
        lambda *a, **k: (fake_portfolio_value_series(*a, **k), {"portfolio_return_basis": "price"}),
    )
    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries)


def test_tracking_error_matches_hand_worked_example(hand_worked_series) -> None:
    value, breakdown = portfolio_utils.compute_tracking_error("alice", "VWRL.L", days=365, include_breakdown=True)

    assert EXPECTED_TRACKING_ERROR == pytest.approx(0.1833030, abs=1e-7)
    assert value == pytest.approx(EXPECTED_TRACKING_ERROR, rel=1e-9)
    assert breakdown["daily_active_standard_deviation"] == pytest.approx(EXPECTED_DAILY_STD, rel=1e-9)
    assert [row["active_return"] for row in breakdown["active_returns"]] == pytest.approx(
        [0.01, -0.01, 0.01, -0.01], abs=1e-12
    )


def test_tracking_error_is_annualised_decimal_not_percent(hand_worked_series) -> None:
    value = portfolio_utils.compute_tracking_error("alice", "VWRL.L", days=365)

    assert 0 < value < 1  # decimal fraction, not percent
    assert value != pytest.approx(EXPECTED_TRACKING_ERROR * 100)
    assert value != pytest.approx(EXPECTED_DAILY_STD * math.sqrt(365))
    assert value != pytest.approx(math.sqrt(0.0004 / 4 * 252))  # population std
    assert value != pytest.approx(EXPECTED_DAILY_STD**2 * 252)  # annualised variance


def test_group_tracking_error_uses_same_formula(hand_worked_series) -> None:
    value = portfolio_utils.compute_group_tracking_error("demo-group", "VWRL.L", days=365)
    assert value == pytest.approx(EXPECTED_TRACKING_ERROR, rel=1e-9)
