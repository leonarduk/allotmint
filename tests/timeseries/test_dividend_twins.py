"""One dividend reported by Yahoo under two ex-dates is stored once (#10926).

FGQI.L/FUSD.L got a second row a week after each quarterly ex-date from
Nov 2025, with the same value; AON, ARES, BUT, IGLT, HMCH and GBDV had
one-off pairs (HMCH's two values differ by 0.6%). Each pair was counted
twice in income and total return.
"""

from __future__ import annotations

import logging

import pandas as pd

from backend.timeseries.corporate_actions import (
    DIVIDEND,
    SPLIT,
    load_corporate_actions,
    merge_actions,
    record_corporate_actions,
)


def _actions(rows, source: str = "Yahoo") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": [pd.Timestamp(day) for day, _, _ in rows],
            "Action": [action for _, action, _ in rows],
            "Value": [value for _, _, value in rows],
            "Currency": ["USD"] * len(rows),
            "Source": [source] * len(rows),
        }
    )


def _divs(*rows) -> pd.DataFrame:
    return _actions([(day, DIVIDEND, value) for day, value in rows])


def _days(frame: pd.DataFrame) -> list[str]:
    return [d.date().isoformat() for d in frame["Date"]]


QUARTERLY = [("2025-08-21", 0.04649), ("2025-11-20", 0.043701), ("2026-02-20", 0.036013), ("2026-05-21", 0.079257)]


def test_fetched_twin_of_a_stored_dividend_is_dropped_and_nothing_changes():
    stored = _divs(*QUARTERLY, ("2026-08-20", 0.042187))
    fetched = _divs(("2026-08-12", 0.042187), ("2026-08-20", 0.042187))

    merged, changed = merge_actions(stored, fetched)

    assert changed is False
    assert _days(merged)[-1] == "2026-08-20"
    assert len(merged) == len(stored)


def test_new_quarter_reported_twice_is_stored_once_on_the_earlier_date():
    stored = _divs(*QUARTERLY)
    fetched = _divs(("2026-08-12", 0.042187), ("2026-08-20", 0.042187))

    merged, changed = merge_actions(stored, fetched)

    assert changed is True
    assert _days(merged)[-1] == "2026-08-12"
    assert len(merged) == len(stored) + 1


def test_near_equal_values_within_one_percent_are_one_payment():
    stored = _divs(("2023-08-03", 4.4899), ("2024-02-01", 5.8265), ("2024-08-01", 5.3782))
    merged, changed = merge_actions(stored, _divs(("2024-08-08", 5.4111)))

    assert changed is False
    assert merged["Value"].tolist() == [4.4899, 5.8265, 5.3782]


def test_a_different_payment_days_apart_is_kept():
    stored = _divs(("2026-02-12", 0.40), ("2026-05-14", 0.40))
    merged, changed = merge_actions(stored, _divs(("2026-05-21", 1.50)))

    assert changed is True
    assert merged["Value"].tolist() == [0.40, 0.40, 1.50]


def test_a_split_near_a_dividend_is_kept():
    stored = _divs(("2026-02-12", 2.0), ("2026-05-14", 2.0))
    merged, _ = merge_actions(stored, _actions([("2026-05-18", SPLIT, 2.0)]))

    assert merged["Action"].tolist() == [DIVIDEND, DIVIDEND, SPLIT]


def test_a_fetched_correction_on_the_stored_date_still_replaces_it():
    stored = _divs(("2026-02-12", 0.40), ("2026-05-14", 0.40))
    merged, changed = merge_actions(stored, _divs(("2026-05-14", 0.401)))

    assert changed is True
    assert merged["Value"].tolist() == [0.40, 0.401]


def test_weekly_payer_is_never_collapsed():
    weekly = [(str(day.date()), 0.10) for day in pd.date_range("2026-06-04", periods=6, freq="7D")]
    stored = _divs(*weekly)
    merged, changed = merge_actions(stored, _divs(("2026-07-16", 0.10)))

    assert changed is True
    assert len(merged) == 7


def test_a_manual_stored_row_is_kept_over_a_yahoo_twin():
    stored = _actions([("2026-05-21", DIVIDEND, 0.079257)], source="Manual")
    merged, changed = merge_actions(stored, _divs(("2026-05-13", 0.079257)))

    assert changed is False
    assert merged["Source"].tolist() == ["Manual"]


def test_record_logs_the_skipped_twin_with_the_instrument(tmp_path, caplog):
    base = str(tmp_path)
    assert record_corporate_actions("FGQI", "L", _divs(*QUARTERLY), base=base) is True

    with caplog.at_level(logging.INFO, logger="backend.timeseries.corporate_actions"):
        assert record_corporate_actions("FGQI", "L", _divs(("2026-05-13", 0.079257)), base=base) is False

    assert "2026-05-13 for FGQI.L: same payment as the one on 2026-05-21" in caplog.text
    assert _days(load_corporate_actions("FGQI", "L", base=base)) == [day for day, _ in QUARTERLY]
