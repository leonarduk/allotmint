"""The cross-source basis guard still rejects a dividend-adjusted second source (#8597, #9340)."""

from __future__ import annotations

import logging

import pandas as pd

from backend.timeseries.source_basis import combine_sources, compatible_rows, same_basis


def _frame(dates, closes, source: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": 0.0,
            "Ticker": "VHYL.L",
            "Source": source,
        }
    )


DAYS = list(pd.bdate_range("2026-09-10", periods=10))
EX_DATE_POS = 5  # a 0.39 dividend on ~58 -> ~0.7% back-adjustment before it
RAW = [58.0 + 0.1 * i for i in range(len(DAYS))]


def _stooq_back_adjusted() -> list[float]:
    factor = 1.0 - 0.39 / RAW[EX_DATE_POS - 1]
    return [round(c * factor, 2) if i < EX_DATE_POS else c for i, c in enumerate(RAW)]


def test_dividend_adjusted_stooq_rows_are_rejected_against_traded_yahoo_cache(caplog):
    """~0.7% off on pre-ex-date rows: inside the general 2% tolerance, but not the traded basis."""
    existing = _frame(DAYS[:8], RAW[:8], "Yahoo")
    stooq = _frame(DAYS, _stooq_back_adjusted(), "Stooq")

    with caplog.at_level(logging.WARNING):
        kept = compatible_rows(existing, stooq, label="VHYL.L")

    assert kept.empty
    assert "Rejecting" in caplog.text


def test_stooq_rows_matching_traded_prices_are_accepted():
    """After the last ex-date Stooq's back-adjustment factor is 1, so its rows may extend the cache."""
    existing = _frame(DAYS[:8], RAW[:8], "Yahoo")
    stooq = _frame(DAYS[6:], RAW[6:], "Stooq")

    kept = compatible_rows(existing, stooq, label="VHYL.L")

    assert len(kept) == 4


def test_combine_sources_keeps_stooq_out_of_a_yahoo_primary():
    yahoo = _frame(DAYS[:7], RAW[:7], "Yahoo")
    stooq = _frame(DAYS[3:], _stooq_back_adjusted()[3:], "Stooq")

    assert not same_basis(yahoo, stooq)
    combined = combine_sources([yahoo, stooq, stooq.iloc[0:0]], label="VHYL.L")

    assert set(combined["Source"]) == {"Yahoo"}


def test_two_traded_sources_keep_the_general_tolerance():
    """A 1% gap between two traded-price feeds is still within BASIS_TOLERANCE (unchanged behaviour)."""
    yahoo = _frame(DAYS[:5], RAW[:5], "Yahoo")
    other = _frame(DAYS[:5], [c * 1.01 for c in RAW[:5]], "AlphaVantage")

    assert same_basis(yahoo, other)


def test_stooq_only_series_is_flagged(caplog):
    stooq = _frame(DAYS, _stooq_back_adjusted(), "Stooq")

    with caplog.at_level(logging.WARNING):
        combined = combine_sources([stooq], label="VHYL.L")

    assert len(combined) == len(DAYS)
    assert "dividend-adjusted" in caplog.text
