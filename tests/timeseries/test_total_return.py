"""Total return from traded closes plus reinvested dividends (#9340)."""

from __future__ import annotations

import pandas as pd
import pytest

from backend.timeseries.total_return import (
    dividends_on_trading_days,
    total_return,
    total_return_index,
)


def _closes(values: list[float], start: str = "2024-03-04") -> pd.Series:
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)))


def test_no_dividends_matches_price_series():
    closes = _closes([100.0, 102.0, 99.0])

    index = total_return_index(closes, pd.Series(dtype=float))

    assert index.tolist() == pytest.approx([100.0, 102.0, 99.0])
    assert total_return(closes, None) == pytest.approx(-0.01)


def test_dividend_is_reinvested_at_ex_date_close():
    # 100 -> ex-date close 98 with a 2.00 dividend -> 99.
    closes = _closes([100.0, 98.0, 99.0])
    dividends = pd.Series({closes.index[1]: 2.0})

    index = total_return_index(closes, dividends, base=1.0)

    # Day 1: (98 + 2) / 100 = 1.0; day 2: 99 / 98.
    assert index.tolist() == pytest.approx([1.0, 1.0, 99.0 / 98.0])
    assert total_return(closes, dividends) == pytest.approx(99.0 / 98.0 - 1.0)


def test_ex_date_on_a_missing_day_snaps_to_next_close():
    closes = _closes([100.0, 101.0, 102.0, 103.0])
    holiday = closes.index[1]
    closes = closes.drop(holiday)
    dividends = pd.Series({holiday: 1.0})

    paid = dividends_on_trading_days(closes, dividends)

    assert paid.tolist() == [0.0, 1.0, 0.0]


def test_dividends_outside_the_window_are_ignored():
    closes = _closes([100.0, 100.0, 100.0])
    dividends = pd.Series(
        {
            closes.index[0] - pd.Timedelta(days=7): 5.0,  # before the window
            closes.index[0]: 5.0,  # holder from the first close is already ex
            closes.index[-1] + pd.Timedelta(days=7): 5.0,  # after the window
        }
    )

    assert total_return(closes, dividends) == pytest.approx(0.0)


def test_total_return_needs_two_closes():
    assert total_return(_closes([100.0]), None) is None
    assert total_return_index(pd.Series(dtype=float), None).empty
