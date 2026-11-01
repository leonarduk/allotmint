"""Patterns over time across reviewed decisions (#10489). Synthetic entries and figures only."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from backend.decision_journal.patterns import (
    MIN_REVIEWED,
    alternative_kind,
    build_patterns,
    trend_watch_state,
)
from backend.decision_journal.store import JournalEntry, Leg, LegOutcome, Review
from tests.backend.decision_journal.test_review import _ADVISORY

START = date(2026, 1, 5)


def _outcome(role, label, ticker, basis, return_pct) -> LegOutcome:
    return LegOutcome(role=role, label=label, ticker=ticker, basis=basis, return_pct=return_pct)


def _review(day: date, horizon: int, chosen: tuple, alternative: tuple) -> Review:
    due = day + timedelta(days=30 * horizon)
    return Review(
        horizon_months=horizon,
        due=due,
        run_on=due,
        legs=[
            _outcome("chosen", "Taken", *chosen),
            _outcome("alternative", "Alternative", *alternative),
        ],
    )


def _entry(
    n: int,
    *,
    trade_type: str = "SELL",
    flagged: Optional[bool] = True,
    chosen: tuple[Optional[str], str, float] = (None, "cash", 0.0),
    alternative: tuple[Optional[str], str, Optional[float]] = ("AAA.L", "total", -1.0),
) -> JournalEntry:
    """Decision ``n`` (``n`` weeks after ``START``): chosen vs one alternative, reviewed at 6 months."""
    day = START + timedelta(weeks=n)
    snapshot: dict = {"instrument": "AAA.L", "trade_type": trade_type}
    if flagged is not None:
        snapshot["trend_watch"] = {"flagged": flagged, "report_date": day.isoformat()}
    return JournalEntry(
        id=f"dj-synth-{n}",
        date=day,
        kind="trade",
        legs=[
            Leg(role="chosen", label="Taken", ticker=chosen[0]),
            Leg(role="alternative", label="Alternative", ticker=alternative[0]),
        ],
        snapshot=snapshot,
        reviews=[_review(day, 6, chosen, alternative)],
    )


# Six flagged sells into cash; the instrument kept returned these over 6 months.
KEPT_RETURNS = [-10.0, -5.0, 3.0, -2.0, 0.0, -8.0]


def _flagged_sells() -> list[JournalEntry]:
    return [_entry(i, alternative=("AAA.L", "total", r)) for i, r in enumerate(KEPT_RETURNS)]


def test_counts_per_horizon_match_a_hand_count():
    patterns = build_patterns(_flagged_sells())
    assert patterns.reviewed_entries == 6
    assert len(patterns.groups) == 1
    group = patterns.groups[0]
    assert (group.kind, group.trade_type, group.trend_watch, group.horizon_months) == ("trade", "SELL", "flagged", 6)
    assert group.split_by_basis is False
    [row] = group.rows
    # Cash at 0% ends above a fall (-10, -5, -2, -8), below a rise (+3) and level with 0.
    assert (row.alternative, row.return_basis) == ("same_instrument", "total")
    assert (row.comparisons, row.above, row.below, row.level) == (6, 4, 1, 1)
    assert (row.first_date, row.last_date) == (START, START + timedelta(weeks=5))


def test_horizons_are_counted_separately():
    entries = _flagged_sells()
    for entry, r in zip(entries, [4.0, 2.0, 1.0, -1.0, 6.0, 5.0]):
        entry.reviews.append(_review(entry.date, 12, (None, "cash", 0.0), ("AAA.L", "total", r)))
    groups = build_patterns(entries).groups
    assert [g.horizon_months for g in groups] == [6, 12]
    six, twelve = groups[0].rows[0], groups[1].rows[0]
    assert (six.above, six.below, six.level) == (4, 1, 1)
    assert (twelve.above, twelve.below, twelve.level) == (1, 5, 0)


def test_below_the_minimum_no_pattern_is_reported():
    patterns = build_patterns(_flagged_sells()[: MIN_REVIEWED - 1])
    assert patterns.reviewed_entries == MIN_REVIEWED - 1
    assert patterns.min_reviewed == MIN_REVIEWED
    assert patterns.groups == []


def test_small_groups_are_left_out_while_large_ones_are_reported():
    buys = [
        _entry(10 + i, trade_type="BUY", chosen=("AAA.L", "total", 1.0), alternative=(None, "cash", 0.0))
        for i in range(MIN_REVIEWED - 1)
    ]
    patterns = build_patterns(_flagged_sells() + buys)
    assert patterns.reviewed_entries == 6 + MIN_REVIEWED - 1
    assert [g.trade_type for g in patterns.groups] == ["SELL"]


def test_mixed_bases_are_counted_apart_and_labelled():
    total = [_entry(i, chosen=("BBB.L", "total", 2.0), alternative=("AAA.L", "total", 1.0)) for i in range(5)]
    mixed = [_entry(10 + i, chosen=("BBB.L", "total", 2.0), alternative=("AAA.L", "price", 3.0)) for i in range(5)]
    [group] = build_patterns(total + mixed).groups
    assert group.split_by_basis is True
    rows = {row.return_basis: row for row in group.rows}
    assert set(rows) == {"mixed", "total"}
    assert (rows["total"].above, rows["total"].below) == (5, 0)
    assert (rows["mixed"].above, rows["mixed"].below) == (0, 5)


def test_trend_watch_flag_splits_groups_and_missing_flag_is_unknown():
    unflagged = [_entry(10 + i, flagged=False) for i in range(5)]
    unknown = [_entry(20 + i, flagged=None) for i in range(5)]
    states = [g.trend_watch for g in build_patterns(_flagged_sells() + unflagged + unknown).groups]
    assert states == ["flagged", "not_flagged", "unknown"]
    assert trend_watch_state({}) == "unknown"
    assert trend_watch_state({"trend_watch": "yes"}) == "unknown"


def test_unpriced_legs_and_unreviewed_entries_are_not_counted():
    entries = _flagged_sells()
    entries[0].reviews[0].legs[1].return_pct = None
    entries.append(_entry(30).model_copy(update={"reviews": []}))
    patterns = build_patterns(entries)
    assert patterns.reviewed_entries == 6
    assert patterns.groups[0].rows[0].comparisons == 5


def test_alternative_kind():
    assert alternative_kind(_outcome("alternative", "x", None, "cash", 0.0), "AAA.L") == "cash"
    assert alternative_kind(_outcome("alternative", "x", "aaa.l", "total", 0.0), "AAA.L") == "same_instrument"
    assert alternative_kind(_outcome("alternative", "x", "CCC.L", "total", 0.0), "AAA.L") == "other"
    assert alternative_kind(_outcome("alternative", "x", "CCC.L", "total", 0.0), None) == "other"


def test_pattern_wording_on_the_page_is_factual():
    locale = Path(__file__).resolve().parents[3] / "frontend" / "src" / "locales" / "en" / "translation.json"
    strings = json.loads(locale.read_text(encoding="utf-8"))["decisionJournal"]
    pattern_text = [value for key, value in strings.items() if key.startswith("patterns")]
    assert pattern_text
    for text in pattern_text:
        assert not _ADVISORY.search(text), text
