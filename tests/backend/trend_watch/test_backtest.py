"""The detector's backtest: further-fall rate after a flag vs the base rate (#10476)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.trend_watch.backtest import HORIZONS, Series, backtest

from .fixtures import INDEX, double_top, rising_benchmark


def test_reports_flag_fall_rate_against_base_rate_per_horizon():
    result = backtest(
        {"TURN.L": Series(closes=double_top(), benchmark_levels=rising_benchmark(), return_basis="total")}
    )

    assert result["tickers_tested"] == 1
    assert result["return_basis"] == {"total": 1}
    assert set(result["horizons"]) == set(HORIZONS)
    one_month = result["horizons"]["1m"]
    # The second leg down keeps falling after the turn, so every flag was followed by a fall...
    assert one_month["flags"] >= 1
    assert one_month["flag_fall_rate"] == 1.0
    # ...while across all weeks (including the climbs) falls were less common.
    assert one_month["base_rate"] < one_month["flag_fall_rate"]
    assert one_month["base_rate"] == round(one_month["base_falls"] / one_month["weeks"], 4)
    six_months = result["horizons"]["6m"]
    assert six_months["days"] == 126
    assert six_months["flags"] >= 1 and six_months["flag_fall_rate"] == 1.0
    assert six_months["weeks"] < one_month["weeks"]


def test_backtest_steps_by_the_configured_run_length():
    from backend.config import TrendWatchConfig

    weekly = backtest({"TURN.L": Series(closes=double_top())})
    fortnightly = backtest({"TURN.L": Series(closes=double_top())}, TrendWatchConfig(new_lookback_days=10))

    assert (weekly["step_days"], fortnightly["step_days"]) == (5, 10)
    assert fortnightly["horizons"]["1m"]["weeks"] < weekly["horizons"]["1m"]["weeks"]


def test_steady_uptrend_raises_no_flags():
    result = backtest({"UP.L": Series(closes=pd.Series(np.linspace(100, 200, len(INDEX)), index=INDEX))})

    assert all(h["flags"] == 0 and h["flag_fall_rate"] is None for h in result["horizons"].values())
    assert result["horizons"]["1m"]["base_rate"] == 0.0


def test_series_with_price_scale_step_or_short_history_is_excluded():
    cliff = double_top().copy()
    cliff.iloc[300:] = cliff.iloc[300:] / 100

    result = backtest({"JEGI.L": Series(closes=cliff), "NEW.L": Series(closes=double_top().iloc[:150])})

    assert result["tickers_tested"] == 0
    assert "price-scale step" in result["excluded"]["JEGI.L"]
    assert result["excluded"]["NEW.L"] == "not enough history"
    assert result["horizons"]["1m"]["base_rate"] is None
