"""Sidecar store for decision-journal entries (#10481).

The plan's ``decisions`` list holds what the owner decided, the alternatives
and their reasoning (``PlanDecision``, linked here by ``id``). Everything else
lives in ``<data_root>/decision_journal/<owner>.json``, so the plan schema only
gains an optional ``id``: the context snapshot taken at decision time, the
legs the review compares, the owner's expectation and the reviews themselves.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.common.investment_plan import DECISION_ID_PATTERN, plans_dir
from backend.common.path_utils import safe_join
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

JOURNAL_DIRNAME = "decision_journal"
#: Trades at or above this many pounds qualify for a "log this decision?" prompt.
DEFAULT_THRESHOLD_GBP = 1000.0
#: Months after the decision at which a follow-up review falls due.
REVIEW_HORIZONS_MONTHS: tuple[int, ...] = (6, 12)

# Same owner-id shape as backend.common.investment_plan; safe_join guards traversal.
_OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,63}$")

LegRole = Literal["chosen", "alternative"]
ExpectationOutcome = Literal["met", "not_met", "unclear"]


class Leg(BaseModel):
    """One option the review values: what was done, or an alternative the owner listed.

    ``ticker`` of ``None`` means the money is held as cash, valued at 0% (no
    interest assumed), so cash drag shows up in the comparison.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: LegRole
    label: str = Field(min_length=1)
    ticker: Optional[str] = None


class ExpectationCheck(BaseModel):
    """An arithmetic test of the expectation: leg ``leg`` returns more than leg ``outperforms``."""

    model_config = ConfigDict(extra="forbid")

    leg: str = Field(min_length=1)
    outperforms: str = Field(min_length=1)


class Expectation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1)
    check: Optional[ExpectationCheck] = None


class LegOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: LegRole
    label: str
    ticker: Optional[str] = None
    #: ``"total"``, ``"price"`` or ``"cash"``; ``None`` when no prices were found.
    basis: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    return_pct: Optional[float] = None
    value_gbp: Optional[float] = None


class Comparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alternative: str
    #: Chosen leg's value minus the alternative's; ``None`` when either is unpriced.
    difference_gbp: Optional[float] = None


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizon_months: int = Field(ge=1)
    due: date
    run_on: date
    legs: list[LegOutcome]
    comparisons: list[Comparison] = Field(default_factory=list)
    #: The basis every priced leg shares, ``"mixed"`` when they differ, ``None`` when nothing priced.
    return_basis: Optional[str] = None
    expectation_outcome: ExpectationOutcome = "unclear"
    summary: list[str] = Field(default_factory=list)
    #: The owner's own note on the review.
    lesson: Optional[str] = None


class JournalEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=DECISION_ID_PATTERN)
    date: date
    kind: Literal["trade", "plan_change", "other"] = "other"
    #: What triggered the entry, e.g. a transaction id; used to stop re-listing it.
    source_ref: Optional[str] = None
    amount_gbp: Optional[float] = Field(default=None, ge=0)
    legs: list[Leg] = Field(default_factory=list)
    expectation: Optional[Expectation] = None
    snapshot: dict[str, Any] = Field(default_factory=dict)
    review_due: list[date] = Field(default_factory=list)
    reviews: list[Review] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_labels_known(self) -> "JournalEntry":
        labels = [leg.label for leg in self.legs]
        if len(set(labels)) != len(labels):
            raise ValueError("Each leg needs a distinct label")
        if sum(leg.role == "chosen" for leg in self.legs) > 1:
            raise ValueError("At most one leg can be the chosen option")
        check = self.expectation.check if self.expectation else None
        if check and not {check.leg, check.outperforms} <= set(labels):
            raise ValueError("The expectation check must name two of the entry's legs")
        return self

    def chosen_leg(self) -> Optional[Leg]:
        return next((leg for leg in self.legs if leg.role == "chosen"), None)


class JournalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold_gbp: float = Field(default=DEFAULT_THRESHOLD_GBP, ge=0)


class Journal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str
    settings: JournalSettings = Field(default_factory=JournalSettings)
    entries: list[JournalEntry] = Field(default_factory=list)
    #: Source refs the owner chose not to log, so they are not listed again.
    dismissed: list[str] = Field(default_factory=list)

    def entry(self, entry_id: str) -> Optional[JournalEntry]:
        return next((e for e in self.entries if e.id == entry_id), None)

    def handled_refs(self) -> set[str]:
        return {e.source_ref for e in self.entries if e.source_ref} | set(self.dismissed)


def journal_dir(data_root: Optional[Path] = None) -> Path:
    """``<data_root>/decision_journal``, beside the ``plans`` directory."""
    return plans_dir(data_root).parent / JOURNAL_DIRNAME


def _journal_path(owner: str, data_root: Optional[Path]) -> Path:
    if not _OWNER_RE.match(owner or ""):
        raise ValueError(f"Invalid owner id {owner!r}")
    return safe_join(journal_dir(data_root), f"{owner}.json")


def load_journal(owner: str, data_root: Optional[Path] = None) -> Journal:
    """The owner's journal, or an empty one when nothing has been logged yet."""
    path = _journal_path(owner, data_root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Journal(owner=owner)
    journal = Journal.model_validate(raw)
    if journal.owner != owner:
        raise ValueError(f"Journal owner {journal.owner!r} does not match {owner!r}")
    return journal


def save_journal(journal: Journal, data_root: Optional[Path] = None) -> Path:
    """Write ``journal`` atomically to ``<data_root>/decision_journal/<owner>.json``."""
    path = _journal_path(journal.owner, data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(journal.model_dump(mode="json", exclude_none=True), indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{journal.owner}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    logger.info("Saved decision journal for %s", sanitise_log_value(journal.owner))
    return path
