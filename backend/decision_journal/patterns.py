"""Patterns over time across reviewed decisions (#10489).

Counts only. For each group of reviewed entries -- by ``kind``, trade type
(``snapshot.trade_type``) and whether the trend-watch list (#10476) had
flagged the instrument when the decision was captured -- and for each review
horizon, it counts how often the option taken ended above, below or level
with each alternative.

* Alternatives are free text, so they are grouped by what they hold: cash,
  the instrument the decision traded, or something else.
* Each count carries its return basis. A comparison of a total-return leg
  with a price-return leg is counted under ``"mixed"``, never folded into
  either basis.
* A count is reported only once at least :data:`MIN_REVIEWED` comparisons
  stand behind it, so no pattern is drawn from one or two cases.

There is no wording here, only figures; the page states them.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.decision_journal.review import combined_basis
from backend.decision_journal.store import JournalEntry, LegOutcome, Review

#: Fewest comparisons behind a reported count.
MIN_REVIEWED = 5

AlternativeKind = Literal["cash", "same_instrument", "other"]
TrendWatchState = Literal["flagged", "not_flagged", "unknown"]


class PatternRow(BaseModel):
    """How the option taken ended against one kind of alternative, on one return basis."""

    model_config = ConfigDict(extra="forbid")

    alternative: AlternativeKind
    #: ``"total"``, ``"price"``, ``"cash"`` or ``"mixed"`` (a total-return leg against a price-return leg).
    return_basis: str
    comparisons: int
    above: int
    below: int
    level: int
    first_date: date
    last_date: date


class PatternGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    trade_type: Optional[str] = None
    trend_watch: TrendWatchState = "unknown"
    horizon_months: int
    rows: list[PatternRow]
    #: True when the rows are on more than one return basis (each row states its own).
    split_by_basis: bool = False


class Patterns(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_reviewed: int = MIN_REVIEWED
    #: Entries with at least one review.
    reviewed_entries: int = 0
    groups: list[PatternGroup] = Field(default_factory=list)


def trend_watch_state(snapshot: dict[str, Any]) -> TrendWatchState:
    """``snapshot["trend_watch"]["flagged"]`` as a state; ``"unknown"`` when it was not captured."""
    recorded = snapshot.get("trend_watch")
    flagged = recorded.get("flagged") if isinstance(recorded, dict) else None
    if flagged is True:
        return "flagged"
    if flagged is False:
        return "not_flagged"
    return "unknown"


def _trade_type(entry: JournalEntry) -> Optional[str]:
    value = entry.snapshot.get("trade_type")
    return str(value).upper() if value else None


def alternative_kind(alternative: LegOutcome, instrument: Optional[str]) -> AlternativeKind:
    if alternative.ticker is None:
        return "cash"
    if instrument and alternative.ticker.upper() == instrument.upper():
        return "same_instrument"
    return "other"


def _outcome(chosen: LegOutcome, alternative: LegOutcome) -> Optional[str]:
    if chosen.return_pct is None or alternative.return_pct is None:
        return None
    if chosen.return_pct > alternative.return_pct:
        return "above"
    if chosen.return_pct < alternative.return_pct:
        return "below"
    return "level"


def _review_comparisons(entry: JournalEntry, review: Review) -> Iterable[tuple[AlternativeKind, str, str]]:
    """``(alternative kind, pair basis, outcome)`` for each priced alternative in ``review``."""
    chosen = next((leg for leg in review.legs if leg.role == "chosen"), None)
    if chosen is None:
        return
    instrument = entry.snapshot.get("instrument")
    for alternative in review.legs:
        if alternative.role != "alternative":
            continue
        outcome = _outcome(chosen, alternative)
        basis = combined_basis([chosen, alternative])
        if outcome is None or basis is None:
            continue
        yield alternative_kind(alternative, instrument), basis, outcome


GroupKey = tuple[str, Optional[str], TrendWatchState, int]
RowKey = tuple[AlternativeKind, str]


def _tally(entries: Iterable[JournalEntry]) -> dict[GroupKey, dict[RowKey, dict[str, Any]]]:
    tally: dict[GroupKey, dict[RowKey, dict[str, Any]]] = defaultdict(dict)
    for entry in entries:
        for review in entry.reviews:
            group = (entry.kind, _trade_type(entry), trend_watch_state(entry.snapshot), review.horizon_months)
            for kind, basis, outcome in _review_comparisons(entry, review):
                row = tally[group].setdefault((kind, basis), {"above": 0, "below": 0, "level": 0, "dates": []})
                row[outcome] += 1
                row["dates"].append(entry.date)
    return tally


def _row(key: RowKey, counts: dict[str, Any]) -> PatternRow:
    dates = counts["dates"]
    return PatternRow(
        alternative=key[0],
        return_basis=key[1],
        comparisons=len(dates),
        above=counts["above"],
        below=counts["below"],
        level=counts["level"],
        first_date=min(dates),
        last_date=max(dates),
    )


def build_patterns(entries: Iterable[JournalEntry], min_reviewed: int = MIN_REVIEWED) -> Patterns:
    """Counts across reviewed ``entries``; rows with fewer than ``min_reviewed`` comparisons are left out."""
    entries = list(entries)
    groups = []
    tally = _tally(entries)
    for kind, trade_type, trend_watch, horizon in sorted(tally, key=lambda g: (g[0], g[1] or "", g[2], g[3])):
        rows = tally[(kind, trade_type, trend_watch, horizon)]
        kept = [_row(key, counts) for key, counts in sorted(rows.items()) if len(counts["dates"]) >= min_reviewed]
        if not kept:
            continue
        groups.append(
            PatternGroup(
                kind=kind,
                trade_type=trade_type,
                trend_watch=trend_watch,
                horizon_months=horizon,
                rows=kept,
                split_by_basis=len({row.return_basis for row in kept}) > 1,
            )
        )
    return Patterns(
        min_reviewed=min_reviewed,
        reviewed_entries=sum(1 for entry in entries if entry.reviews),
        groups=groups,
    )
