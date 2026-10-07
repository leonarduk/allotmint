"""``compatible_rows`` evidence rules for same-source and third-source fetches (#8791)."""

from __future__ import annotations

import logging

import pandas as pd

from backend.timeseries.source_basis import compatible_rows


def _frame(dates, closes, source) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "Close": closes,
            "Ticker": "ABC.L",
            "Source": source,
        }
    )


DAYS = list(pd.bdate_range("2026-09-01", periods=12))
CLOSES = [100.0 + i for i in range(len(DAYS))]


def test_same_source_rows_without_shared_dates_are_kept_with_a_warning(caplog):
    existing = _frame(DAYS[:5], CLOSES[:5], "Yahoo")
    new = _frame(DAYS[7:], CLOSES[7:], "Yahoo")

    with caplog.at_level(logging.WARNING, logger="backend.timeseries.source_basis"):
        kept = compatible_rows(existing, new, label="ABC.L")

    assert len(kept) == len(new)
    assert "without shared-date evidence" in caplog.text


def test_same_source_rows_with_shared_dates_are_kept_silently(caplog):
    existing = _frame(DAYS[:5], CLOSES[:5], "Yahoo")
    new = _frame(DAYS[3:], CLOSES[3:], "Yahoo")

    with caplog.at_level(logging.WARNING, logger="backend.timeseries.source_basis"):
        kept = compatible_rows(existing, new, label="ABC.L")

    assert len(kept) == len(new)
    assert caplog.text == ""


def test_third_source_is_checked_against_a_multi_source_cache(caplog):
    """A new label joining a Yahoo+AlphaVantage cache must still match on shared dates."""
    existing = pd.concat(
        [_frame(DAYS[:4], CLOSES[:4], "Yahoo"), _frame(DAYS[4:6], CLOSES[4:6], "AlphaVantage")],
        ignore_index=True,
    )
    matching = _frame(DAYS[4:9], CLOSES[4:9], "FT")
    off_basis = _frame(DAYS[4:9], [c * 0.75 for c in CLOSES[4:9]], "Stooq")
    no_overlap = _frame(DAYS[9:], CLOSES[9:], "Other")
    new = pd.concat([matching, off_basis, no_overlap], ignore_index=True)

    with caplog.at_level(logging.WARNING, logger="backend.timeseries.source_basis"):
        kept = compatible_rows(existing, new)

    assert set(kept["Source"]) == {"FT"}
    assert "Rejecting" in caplog.text
