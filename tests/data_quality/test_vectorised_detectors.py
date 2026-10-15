"""The vectorised outlier / price-step detectors match per-row reference loops (#10754).

The reference implementations below are plain loops (the price-step ones are
the pre-#10754 code; the outlier one follows the #10962 returns-based rule),
kept here so the faster versions are pinned to exactly the same output on
awkward input: NaNs, flat windows, 10x/100x steps, inverse steps and short
series.
"""

from __future__ import annotations

import math
import statistics

import numpy as np
import pandas as pd
import pytest

from backend.data_quality import price_scale
from backend.timeseries import quality
from backend.timeseries.quality import find_outliers


def _reference_outliers(df: pd.DataFrame, sigma: float, window: int) -> list[dict]:
    """Per-row reference for the returns-based spike-and-revert detector (#10962)."""
    sorted_df = df.sort_values("Date").reset_index(drop=True)
    close = pd.to_numeric(sorted_df["Close"], errors="coerce")
    rows = [(pos, float(v)) for pos, v in enumerate(close) if math.isfinite(v) and v > 0]
    returns = [math.nan] + [math.log(b / a) for (_, a), (_, b) in zip(rows, rows[1:])]
    min_periods = max(3, window // 4)
    out = []
    for i in range(1, len(rows) - 1):
        prior = [r for r in returns[max(0, i - window) : i] if not math.isnan(r)]
        if len(prior) < min_periods:
            continue
        median = statistics.median(prior)
        mad = statistics.median(abs(r - median) for r in prior)
        scale = max(quality.MAD_TO_STD * mad, quality.MIN_RETURN_SCALE)
        ret, nxt = returns[i], returns[i + 1]
        z_score = abs(ret - median) / scale
        spike = z_score > sigma and abs(ret) >= quality.MIN_SPIKE_LOG_RETURN
        undone = abs(ret + nxt) <= (1 - quality.MIN_REVERSION_FRACTION) * abs(ret)
        reverts = (ret > 0) != (nxt > 0) and nxt != 0 and undone
        if spike and reverts:
            pos, value = rows[i]
            row_date = pd.to_datetime(sorted_df["Date"].iloc[pos]).date()
            out.append({"date": row_date.isoformat(), "value": value, "z_score": pytest.approx(z_score)})
    return out


def _reference_steps(closes: pd.Series) -> list[dict]:
    previous = closes.shift(1)
    return [
        {"date": str(day), "previous": float(prev), "value": float(value), "ratio": float(value / prev)}
        for day, prev, value in zip(closes.index[1:], previous.iloc[1:], closes.iloc[1:])
    ]


def _noisy_frame(seed: int, size: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, size)))
    closes[rng.choice(size, 8, replace=False)] *= rng.choice([0.01, 0.1, 3.0, 10.0, 100.0], 8)
    closes[rng.choice(size, 5, replace=False)] = np.nan
    closes[50:80] = 42.0  # flat window: std == 0
    dates = pd.bdate_range("2020-01-01", periods=size)
    # Shuffled rows: find_outliers must sort by Date itself.
    return pd.DataFrame({"Date": dates, "Close": closes}).sample(frac=1.0, random_state=seed)


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize(("sigma", "window"), [(5.0, 20), (1.5, 5), (2.0, 250)])
def test_find_outliers_matches_reference_loop(seed, sigma, window):
    df = _noisy_frame(seed)
    assert find_outliers(df, sigma=sigma, window=window) == _reference_outliers(df, sigma, window)


@pytest.mark.parametrize(
    "closes",
    [
        [],
        [1.0],
        [1.0, 1.0, 1.0],
        [float("nan")] * 5,
        ["1", "x", "3", "100", "2"],
        [1.0, 2.0, float("inf"), 3.0, 4.0, 5.0, 6.0, 7.0],
        [1.0, 2.0, 3.0, float("-inf"), 2.0, 1.0, 50.0, 2.0],
    ],
)
def test_find_outliers_edge_cases_match_reference(closes):
    df = pd.DataFrame({"Date": pd.bdate_range("2024-01-01", periods=len(closes)), "Close": closes})
    assert find_outliers(df, sigma=1.0, window=4) == _reference_outliers(df, 1.0, 4)


def _trending_frame(size: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    # ~60%/yr drift with 1.5% daily noise: the old level z-score flagged
    # dozens of points on a series like this.
    closes = 100 * np.exp(np.cumsum(0.002 + rng.normal(0, 0.015, size)))
    return pd.DataFrame({"Date": pd.bdate_range("2020-01-01", periods=size), "Close": closes})


def test_trending_series_has_no_outliers():
    assert find_outliers(_trending_frame()) == []


def test_breakout_that_holds_is_not_an_outlier():
    df = _trending_frame()
    df.loc[300:, "Close"] *= 1.4  # a 40% jump that sticks is a real move, not a bad tick
    assert find_outliers(df) == []


def test_injected_one_day_spike_is_flagged():
    df = _trending_frame()
    spike_close = df.loc[250, "Close"] * 3.0
    df.loc[250, "Close"] = spike_close
    outliers = find_outliers(df)
    assert [o["date"] for o in outliers] == [df.loc[250, "Date"].date().isoformat()]
    assert outliers[0]["value"] == spike_close
    assert outliers[0]["z_score"] > 50


def _with_spike(jump: float, revert_to: float) -> pd.DataFrame:
    """Flat 100 series: day 100 jumps by ``jump`` and day 101 closes at ``revert_to``, then 100 again."""
    closes = np.full(200, 100.0)
    closes[100] = 100.0 * jump
    closes[101] = revert_to
    return pd.DataFrame({"Date": pd.bdate_range("2020-01-01", periods=200), "Close": closes})


def test_partial_revert_is_not_flagged():
    """A 2x jump that only gives back half the move isn't a one-day bad tick."""
    assert find_outliers(_with_spike(2.0, 100.0 * 2.0**0.5)) == []
    assert len(find_outliers(_with_spike(2.0, 100.0 * 2.0**0.1))) == 1  # 90% undone


def test_move_and_back_below_jump_floor_is_not_flagged():
    """A 10% move-and-back is tick/bid-ask noise even in a flat series with a huge z-score."""
    assert find_outliers(_with_spike(1.10, 100.0)) == []
    assert len(find_outliers(_with_spike(1.20, 100.0))) == 1


def test_spike_on_latest_point_is_not_flagged():
    """A last-day jump can't be confirmed as reverting; LARGE_DAILY_MOVE covers it."""
    df = _trending_frame()
    df.loc[df.index[-1], "Close"] *= 3.0
    assert find_outliers(df) == []


def test_nan_row_next_to_spike_does_not_hide_it():
    df = _trending_frame()
    df.loc[250, "Close"] *= 0.2
    df.loc[251, "Close"] = np.nan
    assert [o["date"] for o in find_outliers(df)] == [df.loc[250, "Date"].date().isoformat()]


@pytest.mark.parametrize("seed", range(6))
def test_scale_steps_and_large_moves_match_reference_loop(seed):
    closes = price_scale.close_series(_noisy_frame(seed))
    steps = _reference_steps(closes)
    exclude = frozenset(s["date"] for s in steps[::37])

    assert price_scale.find_scale_steps(closes, exclude_dates=exclude) == [
        s for s in steps if s["date"] not in exclude and price_scale.is_scale_step(s["ratio"])
    ]
    for threshold in (0.5, 0.05):
        assert price_scale.find_large_moves(closes, threshold, exclude_dates=exclude) == [
            s
            for s in steps
            if s["date"] not in exclude
            and abs(s["ratio"] - 1.0) > threshold
            and not price_scale.is_scale_step(s["ratio"])
        ]


@pytest.mark.parametrize(
    "ratio",
    [10.0, 0.1, 100.0, 0.01, 10**0.1, 10**0.1001, 10**0.5, 10**1.5, 10**2.5, 1.0, 1.26, 0.0, -10.0, math.inf],
)
def test_scale_step_mask_matches_scalar_check(ratio):
    assert bool(price_scale._scale_step_mask(np.array([ratio]))[0]) is price_scale.is_scale_step(ratio)


def test_infinite_close_steps_match_reference():
    closes = pd.Series([100.0, math.inf, 1000.0, 10.0], index=[f"2024-01-0{d}" for d in range(1, 5)])
    steps = _reference_steps(closes)
    assert price_scale.find_scale_steps(closes) == [s for s in steps if price_scale.is_scale_step(s["ratio"])]
    assert price_scale.find_large_moves(closes, 0.5) == [
        s for s in steps if abs(s["ratio"] - 1.0) > 0.5 and not price_scale.is_scale_step(s["ratio"])
    ]


@pytest.mark.parametrize("size", [0, 1, 2])
def test_short_series_steps_match_reference(size):
    closes = pd.Series([100.0, 1000.0][:size], index=["2024-01-01", "2024-01-02"][:size], dtype=float)
    assert list(price_scale._steps(closes)) == _reference_steps(closes)
    assert price_scale.find_scale_steps(closes) == [
        s for s in _reference_steps(closes) if price_scale.is_scale_step(s["ratio"])
    ]
    assert price_scale.latest_move(closes, 0.5) == (_reference_steps(closes)[-1] if size == 2 else None)
