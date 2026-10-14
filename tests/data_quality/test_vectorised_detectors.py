"""The vectorised outlier / price-step detectors match the per-row loops they replaced (#10754).

The reference implementations below are the pre-#10754 loops, kept here so
the faster versions are pinned to exactly the same output on awkward input:
NaNs, flat windows, 10x/100x steps, inverse steps and short series.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backend.common.numeric_utils import is_nan
from backend.data_quality import price_scale
from backend.timeseries.quality import find_outliers


def _reference_outliers(df: pd.DataFrame, sigma: float, window: int) -> list[dict]:
    sorted_df = df.sort_values("Date").reset_index(drop=True)
    close = pd.to_numeric(sorted_df["Close"], errors="coerce")
    min_periods = max(2, window // 2)
    rolling_mean = close.rolling(window=window, min_periods=min_periods).mean()
    rolling_std = close.rolling(window=window, min_periods=min_periods).std()
    out = []
    for pos, value in enumerate(close):
        mean = rolling_mean.iloc[pos]
        std = rolling_std.iloc[pos]
        if is_nan(value) or is_nan(mean) or is_nan(std) or std == 0:
            continue
        z_score = abs(value - mean) / std
        if z_score > sigma:
            row_date = pd.to_datetime(sorted_df["Date"].iloc[pos]).date()
            out.append({"date": row_date.isoformat(), "value": float(value), "z_score": float(z_score)})
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
@pytest.mark.parametrize(("sigma", "window"), [(3.0, 20), (1.5, 5), (2.0, 250)])
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
