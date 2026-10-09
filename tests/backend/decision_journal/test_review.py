"""Follow-up reviews: counterfactual arithmetic, return basis and wording (#10481)."""

from __future__ import annotations

import re
from datetime import date

import pytest

from backend.decision_journal.review import (
    build_review,
    combined_basis,
    due_horizons,
    review_due_dates,
    run_due_reviews,
)
from backend.decision_journal.store import Journal, Leg, LegOutcome
from tests.backend.decision_journal.fixtures import fake_series, sell_entry


def test_six_month_review_matches_hand_worked_example():
    """Sold £10,000 of AAA on 2 Jan 2026, proceeds into BBB; reviewed at the 2 Jul 2026 due date.

    AAA: 100 -> 90 with no dividends: -10.00%, so £10,000 -> £9,000.
    BBB: 50 -> 52 (+£1 dividend reinvested on 1 Apr) -> 55:
         (52 + 1) / 50 = 1.06, then 55 / 52 = 1.057692; 1.06 * 1.057692 = 1.121154 -> +12.12%, £11,211.54.
    Cash: 0% -> £10,000.
    BBB ended £2,211.54 above keeping AAA and £1,211.54 above holding cash.
    """
    entry = sell_entry()
    review = build_review(entry, 6, date(2026, 7, 2), date(2026, 7, 3), fake_series)

    legs = {leg.label: leg for leg in review.legs}
    assert legs["Proceeds to BBB"].return_pct == pytest.approx(12.12)
    assert legs["Proceeds to BBB"].value_gbp == pytest.approx(11_211.54)
    assert legs["Keep holding AAA"].return_pct == pytest.approx(-10.0)
    assert legs["Keep holding AAA"].value_gbp == pytest.approx(9_000.0)
    assert legs["Hold cash"].value_gbp == pytest.approx(10_000.0)
    assert legs["Hold cash"].basis == "cash"
    assert legs["Proceeds to BBB"].end_date == date(2026, 7, 1)

    diffs = {c.alternative: c.difference_gbp for c in review.comparisons}
    assert diffs == {"Keep holding AAA": pytest.approx(2_211.54), "Hold cash": pytest.approx(1_211.54)}
    assert review.return_basis == "total"
    assert review.expectation_outcome == "met"
    text = "\n".join(review.summary)
    assert "total-return basis" in text
    assert "Proceeds to BBB ended £2,211.54 above Keep holding AAA." in text
    assert "cash, 0% interest assumed" in text


def test_twelve_month_review_reports_chosen_leg_below_an_alternative():
    """At 12 months: AAA 100 -> 110 (+10%, £11,000); BBB 1.06 * 50/52 = 1.019231 (£10,192.31)."""
    review = build_review(sell_entry(), 12, date(2027, 1, 2), date(2027, 1, 2), fake_series)
    diffs = {c.alternative: c.difference_gbp for c in review.comparisons}
    assert diffs["Keep holding AAA"] == pytest.approx(-807.69)
    assert review.expectation_outcome == "not_met"
    assert "Proceeds to BBB ended £807.69 below Keep holding AAA." in review.summary


def test_mixed_bases_are_labelled_not_silently_combined():
    entry = sell_entry(
        legs=[
            Leg(role="chosen", label="Proceeds to CCC", ticker="CCC.L"),
            Leg(role="alternative", label="Keep holding AAA", ticker="AAA.L"),
        ],
        expectation=None,
    )
    review = build_review(entry, 6, date(2026, 7, 2), date(2026, 7, 2), fake_series)
    assert review.return_basis == "mixed"
    assert {leg.basis for leg in review.legs} == {"price", "total"}
    text = "\n".join(review.summary)
    assert "different return bases (total vs price)" in text
    assert "(price return," in text and "(total return," in text


def test_cash_does_not_make_a_review_mixed():
    outcomes = [
        LegOutcome(role="chosen", label="a", basis="cash", return_pct=0.0),
        LegOutcome(role="alternative", label="b", basis="price", return_pct=1.0),
    ]
    assert combined_basis(outcomes) == "price"


def test_unpriced_leg_is_reported_and_expectation_unclear():
    entry = sell_entry(
        legs=[
            Leg(role="chosen", label="Proceeds to BBB", ticker="BBB.L"),
            Leg(role="alternative", label="Keep holding AAA", ticker="ZZZ.L"),
        ],
        expectation={"text": "x", "check": {"leg": "Proceeds to BBB", "outperforms": "Keep holding AAA"}},
    )
    review = build_review(entry, 6, date(2026, 7, 2), date(2026, 7, 2), fake_series)
    assert review.expectation_outcome == "unclear"
    assert review.comparisons[0].difference_gbp is None
    assert any("no prices found" in line for line in review.summary)


def test_due_dates_and_due_horizons():
    entry = sell_entry(review_due=[])
    assert review_due_dates(entry.date) == [date(2026, 7, 2), date(2027, 1, 2)]
    assert due_horizons(entry, date(2026, 7, 1)) == []
    assert due_horizons(entry, date(2026, 7, 2)) == [(6, date(2026, 7, 2))]


def test_run_due_reviews_adds_each_horizon_once():
    journal = Journal(owner="alex", entries=[sell_entry()])
    assert [(eid, r.horizon_months) for eid, r in run_due_reviews(journal, date(2027, 2, 1), fake_series)] == [
        ("dj-sell-aaa", 6),
        ("dj-sell-aaa", 12),
    ]
    assert run_due_reviews(journal, date(2027, 3, 1), fake_series) == []
    assert len(journal.entries[0].reviews) == 2


# Advisory or judging language the review text must never use.
_ADVISORY = re.compile(
    r"\b(right|wrong|should|mistake|good|bad|better|worse|recommend\w*|advi[cs]e\w*|regret\w*|"
    r"wise|unwise|smart|correct|incorrect|buy now|sell now|switch)\b",
    re.IGNORECASE,
)


@pytest.mark.parametrize("horizon,due", [(6, date(2026, 7, 2)), (12, date(2027, 1, 2))])
def test_review_wording_is_factual(horizon, due):
    entries = [
        sell_entry(),
        sell_entry(
            legs=[
                Leg(role="chosen", label="CCC", ticker="CCC.L"),
                Leg(role="alternative", label="AAA", ticker="AAA.L"),
            ],
            expectation=None,
        ),
    ]
    for entry in entries:
        text = " ".join(build_review(entry, horizon, due, due, fake_series).summary)
        assert not _ADVISORY.search(text), text
