"""How often has the trend-watch flag been followed by a further fall? (#10476)

Replays the detector's rule (:func:`backend.trend_watch.detect.is_flagged`, with
"new" read from the series exactly as a run without saved state reads it) weekly
over the history of the owner's current holdings, and for each horizon reports:

* ``flag_fall_rate`` -- of the weeks a holding was flagged, the share followed
  by a lower level ``h`` trading days later;
* ``base_rate`` -- the same share across every week, flagged or not.

A flag earns its place only if its rate is clearly above the base rate. Forward
moves use total-return levels where a dividend history is stored, so an income
fund's distributions are not counted as falls; ``return_basis`` counts say how
many series fell back to price returns (#9370). A series with a ~10x/100x step
anywhere in it is left out, since the step would count as a fall.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

import pandas as pd

from backend.config import TrendWatchConfig
from backend.data_quality import price_scale
from backend.trend_watch.detect import (
    SMA_SLOW,
    active_signals,
    clean_series,
    earlier_runs,
    is_flagged,
    iso_dated,
    new_signals,
    signal_frame,
)

HORIZONS = {"1m": 21, "3m": 63, "6m": 126}


def _step(cfg: TrendWatchConfig) -> int:
    """Trading days between replayed runs: the same "one run" the live detector reads earlier runs at."""

    return max(cfg.new_lookback_days, 1)


@dataclass
class Series:
    """One holding's history for the backtest."""

    closes: pd.Series
    levels: Optional[pd.Series] = None
    benchmark_levels: Optional[pd.Series] = None
    return_basis: Optional[str] = None


def _rate(hits: int, total: int) -> Optional[float]:
    return round(hits / total, 4) if total else None


def _empty_counts() -> Dict[str, Dict[str, int]]:
    return {label: {"flags": 0, "flag_falls": 0, "weeks": 0, "falls": 0} for label in HORIZONS}


def backtest_series(series: Series, cfg: TrendWatchConfig, counts: Dict[str, Dict[str, int]]) -> int:
    """Add one holding's weekly outcomes to ``counts``; return how many flags it raised."""

    closes = clean_series(series.closes)
    frame = signal_frame(closes, series.benchmark_levels, cfg)
    levels = clean_series(series.levels) if series.levels is not None else closes
    levels = levels.reindex(closes.index.union(levels.index)).ffill().reindex(closes.index)
    flags = 0
    step = _step(cfg)
    for position in range(SMA_SLOW + step * max(cfg.memory_runs, 1), len(frame), step):
        active = active_signals(frame, position)
        earlier = {name for run in earlier_runs(frame, position, cfg) for name in run}
        flagged = is_flagged(active, new_signals(active, earlier), cfg)
        flags += flagged
        start = levels.iloc[position]
        for label, days in HORIZONS.items():
            if position + days >= len(levels) or pd.isna(start):
                continue
            fell = bool(levels.iloc[position + days] < start)
            bucket = counts[label]
            bucket["weeks"] += 1
            bucket["falls"] += fell
            if flagged:
                bucket["flags"] += 1
                bucket["flag_falls"] += fell
    return flags


def backtest(series_by_ticker: Mapping[str, Series], cfg: Optional[TrendWatchConfig] = None) -> Dict[str, Any]:
    """The detector's track record over ``series_by_ticker``, horizon by horizon."""

    cfg = cfg or TrendWatchConfig()
    counts = _empty_counts()
    bases: Counter[str] = Counter()
    excluded: Dict[str, str] = {}
    tested = 0
    for ticker, series in series_by_ticker.items():
        closes = clean_series(series.closes)
        if len(closes) < SMA_SLOW + _step(cfg) + min(HORIZONS.values()):
            excluded[ticker] = "not enough history"
            continue
        steps = price_scale.find_scale_steps(iso_dated(closes))
        if steps:
            excluded[ticker] = f"price-scale step on {steps[0]['date']} (data problem)"
            continue
        backtest_series(series, cfg, counts)
        bases[series.return_basis or "price"] += 1
        tested += 1
    horizons = {
        label: {
            "days": HORIZONS[label],
            "flags": bucket["flags"],
            "flag_falls": bucket["flag_falls"],
            "flag_fall_rate": _rate(bucket["flag_falls"], bucket["flags"]),
            "weeks": bucket["weeks"],
            "base_falls": bucket["falls"],
            "base_rate": _rate(bucket["falls"], bucket["weeks"]),
        }
        for label, bucket in counts.items()
    }
    return {
        "tickers_tested": tested,
        "excluded": excluded,
        "step_days": _step(cfg),
        "return_basis": dict(bases),
        "horizons": horizons,
    }
