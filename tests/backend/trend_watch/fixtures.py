"""Synthetic price fixtures for the trend-watch tests (#10476).

Storage is isolated by ``isolate_trend_watch`` in ``tests/conftest.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DAYS = 700
INDEX = pd.bdate_range("2023-01-02", periods=DAYS)
# The first day of the second leg down's death cross in ``double_top`` (+1, as a slice end).
FRESH_TURN_END = 576


def double_top() -> pd.Series:
    """Up, down, a partial recovery, then down again: a fresh death cross under a falling 200-day average."""

    return pd.Series(
        np.r_[
            np.linspace(100, 160, 250),
            np.linspace(160, 110, 150),
            np.linspace(110, 120, 120),
            np.linspace(120, 90, 180),
        ],
        index=INDEX,
    )


def rising_benchmark() -> pd.Series:
    return pd.Series(np.linspace(100, 130, DAYS), index=INDEX)


def falling_with(series: pd.Series) -> pd.Series:
    """A benchmark that moves exactly with ``series``: any fall is market-wide."""

    return series.copy()


def rsi_dip() -> pd.Series:
    """A steady uptrend with a sharp five-day dip at the end: RSI falls, the trend does not turn."""

    closes = np.linspace(100, 160, DAYS)
    closes[-5:] = closes[-6] * np.array([0.98, 0.96, 0.94, 0.93, 0.92])
    return pd.Series(closes, index=INDEX)


def pence_cliff() -> pd.Series:
    """``double_top`` with its last 3 closes quoted in pounds instead of pence (a JEGI.L-style cliff)."""

    closes = double_top().iloc[:FRESH_TURN_END].copy()
    closes.iloc[-3:] = closes.iloc[-3:] / 100
    return closes
