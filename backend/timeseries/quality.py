"""Read-only data quality checks for cached meta timeseries.

Pure functions operating on a DataFrame already loaded from the cache
(see :func:`backend.timeseries.cache.load_cached_meta_timeseries_full`).
Nothing here mutates the input DataFrame or touches storage.
"""

from __future__ import annotations

import warnings
from datetime import date
from typing import TypedDict

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from backend.utils.market_holidays import business_days_between

DEFAULT_GAP_THRESHOLD_DAYS = 1
# Robust z-score (median/MAD of trailing daily log-returns) beyond which a
# one-day move is a spike. Daily returns are fat-tailed, so 3 flagged
# ordinary volatile days; 5 plus the jump floor and revert test below keeps
# OUTLIERS to plausible bad ticks (#10962).
DEFAULT_OUTLIER_SIGMA = 5.0
DEFAULT_ROLLING_WINDOW = 20
# Scales a median absolute deviation to a normal-equivalent std dev.
MAD_TO_STD = 1.4826
# Floor on the robust return scale (log-return units, ~0.5%) so a flat or
# barely-moving window (MAD == 0) doesn't turn every tiny move into a spike.
MIN_RETURN_SCALE = 0.005
# Share of a spike the next day's return must undo to count as a revert.
MIN_REVERSION_FRACTION = 0.8
# Smallest jump (log-return, ~16%) worth flagging: below this, a one-day
# move-and-back is bid/ask bounce or tick-size noise, not a bad print.
MIN_SPIKE_LOG_RETURN = 0.15


class GapPeriod(TypedDict):
    start: str
    end: str
    missing_business_days: int


class Outlier(TypedDict):
    date: str
    value: float
    z_score: float


class TimeseriesQuality(TypedDict):
    ticker: str
    exchange: str
    total_points: int
    first_date: str | None
    last_date: str | None
    gap_count: int
    gaps: list[GapPeriod]
    duplicate_dates: list[str]
    outliers: list[Outlier]


def _to_date_series(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df["Date"]).dt.date


def find_duplicate_dates(df: pd.DataFrame) -> list[date]:
    """Return sorted dates that appear more than once in the timeseries."""
    if df.empty:
        return []
    dates = _to_date_series(df)
    counts = dates.value_counts()
    return sorted(counts[counts > 1].index)


def find_gaps(
    df: pd.DataFrame,
    gap_threshold_days: int = DEFAULT_GAP_THRESHOLD_DAYS,
    exchange: str | None = None,
) -> list[GapPeriod]:
    """Return contiguous runs of missing trading days longer than the threshold.

    Weekends and ``exchange``'s holidays (see
    :func:`backend.utils.market_holidays.exchange_holidays`; the UK calendar
    when the exchange is unknown) are excluded from "expected" days, so a gap
    over a weekend or a market closure is never reported (#10961).
    """
    if df.empty:
        return []
    present = set(_to_date_series(df))
    if len(present) < 2:
        return []
    first_date, last_date = min(present), max(present)
    expected = business_days_between(first_date, last_date, exchange)
    missing = [d for d in expected if d not in present]
    if not missing:
        return []

    expected_index = {d: i for i, d in enumerate(expected)}
    runs: list[list[date]] = []
    current: list[date] = [missing[0]]
    for prev, curr in zip(missing, missing[1:]):
        if expected_index[curr] == expected_index[prev] + 1:
            current.append(curr)
        else:
            runs.append(current)
            current = [curr]
    runs.append(current)

    return [
        GapPeriod(
            start=run[0].isoformat(),
            end=run[-1].isoformat(),
            missing_business_days=len(run),
        )
        for run in runs
        if len(run) > gap_threshold_days
    ]


def _trailing_robust_z(returns: np.ndarray, rows: np.ndarray, window: int, min_periods: int) -> np.ndarray:
    """Robust z-score of ``returns[rows]`` against the ``window`` returns before each row.

    The window excludes the row's own return so a spike cannot inflate the
    scale it is measured against. A row with fewer than ``min_periods``
    prior finite returns gets NaN.
    """
    padded = np.concatenate([np.full(window, np.nan), returns])
    # Row i's window is padded[i : i + window], i.e. returns[i - window : i].
    windows = sliding_window_view(padded, window)[rows]
    enough = np.count_nonzero(~np.isnan(windows), axis=1) >= min_periods
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN windows
        medians = np.nanmedian(windows, axis=1)
        mads = np.nanmedian(np.abs(windows - medians[:, None]), axis=1)
    scales = np.maximum(MAD_TO_STD * mads, MIN_RETURN_SCALE)
    z_scores = np.abs(returns[rows] - medians) / scales
    z_scores[~enough] = np.nan
    return z_scores


def find_outliers(
    df: pd.DataFrame,
    sigma: float = DEFAULT_OUTLIER_SIGMA,
    window: int = DEFAULT_ROLLING_WINDOW,
) -> list[Outlier]:
    """Return single-day price spikes that revert the next day.

    Detection runs on daily log-returns, not price levels: a level z-score
    flags every trend or breakout, so ~1,057 healthy series each reported a
    median of 17 "outliers" (#10962). A point is flagged when

    * its return deviates more than ``sigma`` robust std devs (1.4826 * MAD,
      floored at :data:`MIN_RETURN_SCALE`) from the median of the trailing
      ``window`` returns and is at least :data:`MIN_SPIKE_LOG_RETURN`, and
    * the next day's return has the opposite sign and undoes at least
      :data:`MIN_REVERSION_FRACTION` of the jump.

    ``z_score`` is the robust z of the spike-day return. The latest point
    can't be confirmed as reverting and is never flagged; LARGE_DAILY_MOVE
    and PRICE_SCALE_SUSPECT cover big or 10x/100x moves, including the last
    day. Rows with a missing, non-finite or non-positive Close are dropped
    before returns are taken, so they neither hide nor fake a spike.

    Uses ``min_periods=max(3, window // 4)`` prior returns so a short series
    still gets coverage; the median/MAD for those early points are noisier.
    """
    if df.empty or "Close" not in df.columns:
        return []
    sorted_df = df.sort_values("Date").reset_index(drop=True)
    values = pd.to_numeric(sorted_df["Close"], errors="coerce").to_numpy(dtype=float)
    keep = np.flatnonzero(np.isfinite(values) & (values > 0))
    if keep.size < 3:
        return []
    closes = values[keep]

    # Vectorised: a per-row .iloc loop dominated GET /data-quality/issues on
    # ~1,000 cached series (#10754). returns[i] is the move into closes[i].
    # The cheap jump-and-revert test runs first so the (slow) rolling
    # median/MAD is only computed for the handful of candidate rows.
    returns = np.concatenate([[np.nan], np.diff(np.log(closes))])
    next_returns = np.concatenate([returns[1:], [np.nan]])
    with np.errstate(invalid="ignore"):
        candidates = np.flatnonzero(
            (np.abs(returns) >= MIN_SPIKE_LOG_RETURN)
            & (np.sign(next_returns) == -np.sign(returns))
            & (np.abs(returns + next_returns) <= (1.0 - MIN_REVERSION_FRACTION) * np.abs(returns))
        )
    if candidates.size == 0:
        return []
    z_scores = _trailing_robust_z(returns, candidates, window, max(3, window // 4))
    flagged = z_scores > sigma  # NaN (too little history) is never flagged
    hits, hit_z = candidates[flagged], z_scores[flagged]
    if hits.size == 0:
        return []
    hit_dates = pd.to_datetime(sorted_df["Date"].iloc[keep[hits]])
    return [
        Outlier(date=row_date.date().isoformat(), value=float(closes[pos]), z_score=float(z))
        for pos, z, row_date in zip(hits, hit_z, hit_dates)
    ]


def compute_quality(
    df: pd.DataFrame,
    ticker: str,
    exchange: str,
    gap_threshold_days: int = DEFAULT_GAP_THRESHOLD_DAYS,
    outlier_sigma: float = DEFAULT_OUTLIER_SIGMA,
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
) -> TimeseriesQuality:
    """Compute the full set of data quality metrics for one ticker's timeseries."""
    if df.empty:
        return TimeseriesQuality(
            ticker=ticker,
            exchange=exchange,
            total_points=0,
            first_date=None,
            last_date=None,
            gap_count=0,
            gaps=[],
            duplicate_dates=[],
            outliers=[],
        )

    dates = _to_date_series(df)
    gaps = find_gaps(df, gap_threshold_days=gap_threshold_days, exchange=exchange)

    return TimeseriesQuality(
        ticker=ticker,
        exchange=exchange,
        total_points=len(df),
        first_date=dates.min().isoformat(),
        last_date=dates.max().isoformat(),
        gap_count=len(gaps),
        gaps=gaps,
        duplicate_dates=[d.isoformat() for d in find_duplicate_dates(df)],
        outliers=find_outliers(df, sigma=outlier_sigma, window=rolling_window),
    )
