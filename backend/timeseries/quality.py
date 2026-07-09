"""Read-only data quality checks for cached meta timeseries.

Pure functions operating on a DataFrame already loaded from the cache
(see :func:`backend.timeseries.cache.load_cached_meta_timeseries_full`).
Nothing here mutates the input DataFrame or touches storage.
"""

from __future__ import annotations

from datetime import date
from typing import TypedDict

import pandas as pd

from backend.utils.uk_holidays import uk_business_days_between

DEFAULT_GAP_THRESHOLD_DAYS = 1
DEFAULT_OUTLIER_SIGMA = 3.0
DEFAULT_ROLLING_WINDOW = 20


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


def find_gaps(df: pd.DataFrame, gap_threshold_days: int = DEFAULT_GAP_THRESHOLD_DAYS) -> list[GapPeriod]:
    """Return contiguous runs of missing UK business days longer than the threshold.

    Weekends and UK bank holidays are excluded from "expected" days, so a gap
    over a weekend or holiday is never reported.
    """
    if df.empty:
        return []
    present = set(_to_date_series(df))
    if len(present) < 2:
        return []
    first_date, last_date = min(present), max(present)
    expected = uk_business_days_between(first_date, last_date)
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


def find_outliers(
    df: pd.DataFrame,
    sigma: float = DEFAULT_OUTLIER_SIGMA,
    window: int = DEFAULT_ROLLING_WINDOW,
) -> list[Outlier]:
    """Return points whose Close deviates more than ``sigma`` rolling std devs
    from the trailing rolling mean."""
    if df.empty or "Close" not in df.columns:
        return []
    sorted_df = df.sort_values("Date").reset_index(drop=True)
    close = pd.to_numeric(sorted_df["Close"], errors="coerce")
    min_periods = max(2, window // 2)
    rolling_mean = close.rolling(window=window, min_periods=min_periods).mean()
    rolling_std = close.rolling(window=window, min_periods=min_periods).std()

    outliers: list[Outlier] = []
    for idx, value in close.items():
        mean = rolling_mean[idx]
        std = rolling_std[idx]
        if pd.isna(value) or pd.isna(mean) or pd.isna(std) or std == 0:
            continue
        z_score = abs(value - mean) / std
        if z_score > sigma:
            row_date = pd.to_datetime(sorted_df["Date"][idx]).date()
            outliers.append(Outlier(date=row_date.isoformat(), value=float(value), z_score=float(z_score)))
    return outliers


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
    gaps = find_gaps(df, gap_threshold_days=gap_threshold_days)

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
