"""6- and 12-month follow-up reviews of logged decisions (#10481).

A review values the decision's amount in each leg (the option taken and each
alternative the owner listed) from the decision date to the due date, and
reports the arithmetic: each leg's return with its return basis, and how far
the option taken ended above or below each alternative. Cash legs are valued
at 0% (no interest assumed), which is how cash drag shows up.

The wording reports figures only. It never calls a decision right or wrong
and never suggests a trade; ``test_review`` checks the text for that.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd
from dateutil.relativedelta import relativedelta

from backend.decision_journal.prices import SeriesLoader, load_return_series
from backend.decision_journal.store import (
    REVIEW_HORIZONS_MONTHS,
    Comparison,
    ExpectationOutcome,
    Journal,
    JournalEntry,
    Leg,
    LegOutcome,
    Review,
)

CASH_BASIS = "cash"
MIXED_BASIS = "mixed"


def review_due_dates(decided: date) -> list[date]:
    return [decided + relativedelta(months=months) for months in REVIEW_HORIZONS_MONTHS]


def leg_outcome(leg: Leg, start: date, end: date, amount: Optional[float], load_series: SeriesLoader) -> LegOutcome:
    """``leg``'s return from the first close on/after ``start`` to the last on/before ``end``."""
    base = LegOutcome(role=leg.role, label=leg.label, ticker=leg.ticker)
    if leg.ticker is None:
        return base.model_copy(
            update={"basis": CASH_BASIS, "start_date": start, "end_date": end, "return_pct": 0.0, "value_gbp": amount}
        )
    closes, basis = load_series(leg.ticker, start, end)
    closes = closes.dropna()
    closes = closes[(closes.index >= pd.Timestamp(start)) & (closes.index <= pd.Timestamp(end))].sort_index()
    if len(closes) < 2:
        return base
    growth = float(closes.iloc[-1]) / float(closes.iloc[0])
    return base.model_copy(
        update={
            "basis": basis,
            "start_date": closes.index[0].date(),
            "end_date": closes.index[-1].date(),
            "return_pct": round((growth - 1) * 100, 2),
            "value_gbp": None if amount is None else round(amount * growth, 2),
        }
    )


def combined_basis(outcomes: list[LegOutcome]) -> Optional[str]:
    """The basis all priced investment legs share, ``"mixed"`` if they differ.

    Cash legs carry no basis of their own, so they do not make a review mixed.
    """
    bases = {o.basis for o in outcomes if o.basis and o.basis != CASH_BASIS}
    if len(bases) > 1:
        return MIXED_BASIS
    if bases:
        return bases.pop()
    return CASH_BASIS if any(o.basis == CASH_BASIS for o in outcomes) else None


def _comparisons(outcomes: list[LegOutcome]) -> list[Comparison]:
    chosen = next((o for o in outcomes if o.role == "chosen"), None)
    if chosen is None:
        return []
    return [
        Comparison(
            alternative=alt.label,
            difference_gbp=(
                None
                if chosen.value_gbp is None or alt.value_gbp is None
                else round(chosen.value_gbp - alt.value_gbp, 2)
            ),
        )
        for alt in outcomes
        if alt.role == "alternative"
    ]


def expectation_outcome(entry: JournalEntry, outcomes: list[LegOutcome]) -> ExpectationOutcome:
    """``met``/``not_met`` from the recorded check; ``unclear`` without one or without prices."""
    check = entry.expectation.check if entry.expectation else None
    if check is None:
        return "unclear"
    by_label = {o.label: o.return_pct for o in outcomes}
    first, second = by_label.get(check.leg), by_label.get(check.outperforms)
    if first is None or second is None:
        return "unclear"
    return "met" if first > second else "not_met"


def _gbp(value: float) -> str:
    return f"£{value:,.2f}"


def _leg_line(outcome: LegOutcome, amount: Optional[float]) -> str:
    if outcome.return_pct is None:
        return f"{outcome.label} ({outcome.ticker}): no prices found for this period."
    if outcome.basis == CASH_BASIS:
        where, basis = "cash, 0% interest assumed", "cash"
    else:
        where, basis = outcome.ticker, f"{outcome.basis} return"
    period = f"{outcome.start_date} to {outcome.end_date}"
    line = f"{outcome.label} ({where}): {outcome.return_pct:+.2f}% ({basis}, {period})"
    if amount is not None and outcome.value_gbp is not None:
        line += f"; {_gbp(amount)} would be {_gbp(outcome.value_gbp)}"
    return line + "."


def _basis_line(basis: Optional[str], horizon: int, due: date) -> str:
    head = f"{horizon}-month review to {due}."
    if basis == MIXED_BASIS:
        return head + " The options are on different return bases (total vs price); each line states its own."
    if basis in (None, CASH_BASIS):
        return head
    return head + f" Investment returns are on a {basis}-return basis."


_OUTCOME_TEXT = {"met": "met", "not_met": "not met", "unclear": "unclear (no checkable figures)"}


def summary_lines(entry: JournalEntry, review: Review) -> list[str]:
    lines = [_basis_line(review.return_basis, review.horizon_months, review.due)]
    lines += [_leg_line(outcome, entry.amount_gbp) for outcome in review.legs]
    chosen = entry.chosen_leg()
    for comparison in review.comparisons:
        if chosen is None or comparison.difference_gbp is None:
            continue
        side = "above" if comparison.difference_gbp >= 0 else "below"
        lines.append(f"{chosen.label} ended {_gbp(abs(comparison.difference_gbp))} {side} {comparison.alternative}.")
    if entry.expectation:
        lines.append(f'Stated expectation "{entry.expectation.text}": {_OUTCOME_TEXT[review.expectation_outcome]}.')
    return lines


def build_review(
    entry: JournalEntry, horizon_months: int, due: date, run_on: date, load_series: SeriesLoader = load_return_series
) -> Review:
    outcomes = [leg_outcome(leg, entry.date, due, entry.amount_gbp, load_series) for leg in entry.legs]
    review = Review(
        horizon_months=horizon_months,
        due=due,
        run_on=run_on,
        legs=outcomes,
        comparisons=_comparisons(outcomes),
        return_basis=combined_basis(outcomes),
        expectation_outcome=expectation_outcome(entry, outcomes),
    )
    review.summary = summary_lines(entry, review)
    return review


def due_horizons(entry: JournalEntry, as_of: date) -> list[tuple[int, date]]:
    """``(horizon_months, due)`` pairs that are due by ``as_of`` and not reviewed yet."""
    done = {r.horizon_months for r in entry.reviews}
    return [
        (months, due)
        for months, due in zip(REVIEW_HORIZONS_MONTHS, entry.review_due or review_due_dates(entry.date))
        if due <= as_of and months not in done
    ]


def run_due_reviews(
    journal: Journal, as_of: date, load_series: SeriesLoader = load_return_series
) -> list[tuple[str, Review]]:
    """Add every due review to ``journal`` (in memory) and return ``(entry_id, review)`` pairs."""
    added = []
    for entry in journal.entries:
        for months, due in due_horizons(entry, as_of):
            review = build_review(entry, months, due, as_of, load_series)
            entry.reviews.append(review)
            added.append((entry.id, review))
    return added
