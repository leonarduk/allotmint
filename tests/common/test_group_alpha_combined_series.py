"""Group alpha / tracking error come from the combined series, not a mean (#7306).

``/performance-group/{slug}/alpha`` and ``/performance-group/{slug}/tracking-error``
(``backend/routes/performance.py:group_alpha`` / ``group_tracking_error``) call
``portfolio_utils.compute_group_alpha_vs_benchmark`` /
``compute_group_tracking_error``. Those run ``_alpha_vs_benchmark`` /
``_tracking_error`` with ``group=True``, which builds ONE value series from
``group_portfolio.build_group_portfolio`` (every member's holdings merged)
via ``_portfolio_value_series``. These tests pin that: with two owners whose
alphas differ and whose starting values differ, the group figure must equal
the value computed from the summed series and must NOT equal the mean of the
per-owner figures.

Worked numbers (benchmark 100 -> 103, so benchmark cumulative return = 3%):

    alice: 10 x AAA  1000 -> 1100 -> 990  -> 1210   cum 21%   alpha +18%
    bob:    3 x BBB  3000 -> 3000 -> 3150 -> 3000   cum  0%   alpha  -3%
    group:           4000 -> 4100 -> 4140 -> 4210   cum 5.25% alpha 2.25%

    mean of per-owner alphas = (18% - 3%) / 2 = 7.5%  != 2.25%
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backend.common import portfolio_utils
from backend.routes import performance

DATES = pd.bdate_range("2024-01-01", periods=4)
PRICES = {
    ("AAA", "L"): [100.0, 110.0, 99.0, 121.0],
    ("BBB", "L"): [1000.0, 1000.0, 1050.0, 1000.0],
    ("VWRL", "L"): [100.0, 101.0, 102.0, 103.0],
}
OWNER_HOLDINGS = {
    "alice": [{"ticker": "AAA.L", "units": 10}],
    "bob": [{"ticker": "BBB.L", "units": 3}],
}

EXPECTED_GROUP_ALPHA = (4210.0 / 4000.0 - 1) - 0.03
MEAN_OWNER_ALPHA = ((0.21 - 0.03) + (0.0 - 0.03)) / 2


def _portfolio(owners: list[str]) -> dict:
    return {"accounts": [{"owner": o, "holdings": OWNER_HOLDINGS[o]} for o in owners]}


@pytest.fixture
def two_owner_group(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.common.instrument_api as instrument_api

    monkeypatch.setattr(
        portfolio_utils.portfolio_mod,
        "build_owner_portfolio",
        lambda name, *, pricing_date=None, **_: _portfolio([name]),
    )
    monkeypatch.setattr(
        portfolio_utils.group_portfolio,
        "build_group_portfolio",
        lambda slug, *, pricing_date=None, **_: _portfolio(["alice", "bob"]),
    )
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {}, raising=False)
    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda ticker, snapshot: tuple(ticker.split(".", 1)),
    )
    monkeypatch.setattr(portfolio_utils, "_detect_single_day_flash_crash", None)

    def fake_load_meta_timeseries(ticker: str, exchange: str, days: int) -> pd.DataFrame:
        closes = PRICES.get((ticker, exchange))
        if closes is None:
            return pd.DataFrame()
        return pd.DataFrame({"Date": DATES, "Close": closes})

    monkeypatch.setattr(portfolio_utils, "load_meta_timeseries", fake_load_meta_timeseries)


def _annualised_te(values: list[float]) -> float:
    port_ret = pd.Series(values).pct_change().dropna()
    bench_ret = pd.Series(PRICES[("VWRL", "L")]).pct_change().dropna()
    return float((port_ret - bench_ret).std() * math.sqrt(252))


def test_group_alpha_is_combined_series_not_mean_of_owner_alphas(two_owner_group) -> None:
    alice = portfolio_utils.compute_alpha_vs_benchmark("alice", "VWRL.L", days=365)
    bob = portfolio_utils.compute_alpha_vs_benchmark("bob", "VWRL.L", days=365)
    group = portfolio_utils.compute_group_alpha_vs_benchmark("family", "VWRL.L", days=365)

    assert alice == pytest.approx(0.18)
    assert bob == pytest.approx(-0.03)
    assert group == pytest.approx(EXPECTED_GROUP_ALPHA, rel=1e-9)
    assert group != pytest.approx(MEAN_OWNER_ALPHA)
    assert group != pytest.approx((alice + bob) / 2)


def test_group_tracking_error_is_combined_series_not_mean(two_owner_group) -> None:
    alice = portfolio_utils.compute_tracking_error("alice", "VWRL.L", days=365)
    bob = portfolio_utils.compute_tracking_error("bob", "VWRL.L", days=365)
    group = portfolio_utils.compute_group_tracking_error("family", "VWRL.L", days=365)

    combined_values = list(np.add([1000.0, 1100.0, 990.0, 1210.0], [3000.0, 3000.0, 3150.0, 3000.0]))
    assert alice == pytest.approx(_annualised_te([1000.0, 1100.0, 990.0, 1210.0]), rel=1e-9)
    assert bob == pytest.approx(_annualised_te([3000.0, 3000.0, 3150.0, 3000.0]), rel=1e-9)
    assert group == pytest.approx(_annualised_te(combined_values), rel=1e-9)
    assert group != pytest.approx((alice + bob) / 2)


def test_group_routes_return_combined_series_values(two_owner_group) -> None:
    alpha = performance.group_alpha("family", benchmark="VWRL.L", days=365)
    te = performance.group_tracking_error("family", benchmark="VWRL.L", days=365)

    assert alpha["alpha_vs_benchmark"] == pytest.approx(EXPECTED_GROUP_ALPHA, rel=1e-9)
    assert alpha["portfolio_cumulative_return"] == pytest.approx(4210.0 / 4000.0 - 1)
    assert alpha["alpha_vs_benchmark"] != pytest.approx(MEAN_OWNER_ALPHA)
    assert [row["portfolio_return"] for row in te["active_returns"]] == pytest.approx(
        [4100.0 / 4000.0 - 1, 4140.0 / 4100.0 - 1, 4210.0 / 4140.0 - 1]
    )
