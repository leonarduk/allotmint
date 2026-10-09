"""Owner-confirmed writes for the decision journal (#10481).

This is the only path that adds a journal decision to the plan. It runs on an
explicit confirmation carrying the owner's own reasoning; drafts from
:mod:`backend.decision_journal.capture` are never saved by themselves.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.common.investment_plan import (
    DECISION_ID_PATTERN,
    InvestmentPlan,
    PlanDecision,
    load_plan,
    parse_plan,
    save_plan,
)
from backend.decision_journal.review import review_due_dates
from backend.decision_journal.store import Expectation, JournalEntry, JournalSettings, Leg, load_journal, save_journal


class DuplicateDecisionError(ValueError):
    """The decision id is already in the plan or the journal."""


class ConfirmDecision(BaseModel):
    """A draft the owner has completed and confirmed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    #: Must be sent as ``true``: the owner's explicit confirmation.
    confirmed: Literal[True]
    id: str = Field(pattern=DECISION_ID_PATTERN)
    date: date
    kind: Literal["trade", "plan_change", "other"] = "other"
    source_ref: Optional[str] = None
    decision: str = Field(min_length=1)
    alternatives: list[str] = Field(default_factory=list)
    #: The owner's reasoning, in their words; required.
    reason: str = Field(min_length=1)
    amount_gbp: Optional[float] = Field(default=None, ge=0)
    legs: list[Leg] = Field(default_factory=list)
    expectation: Optional[Expectation] = None
    snapshot: dict[str, Any] = Field(default_factory=dict)


def _plan_with_decision(plan: InvestmentPlan, body: ConfirmDecision) -> InvestmentPlan:
    decision = PlanDecision(
        id=body.id, date=body.date, decision=body.decision, alternatives=body.alternatives, reason=body.reason
    )
    data = plan.to_dict()
    data["decisions"] = [*data.get("decisions", []), decision.model_dump(mode="json", exclude_none=True)]
    return parse_plan(data, plan.owner)


def confirm_decision(owner: str, body: ConfirmDecision, data_root: Optional[Path] = None) -> JournalEntry:
    """Append the decision to the plan and its context to the journal.

    Raises :class:`~backend.common.investment_plan.PlanNotFoundError` when the
    owner has no plan, and :class:`DuplicateDecisionError` when the journal
    already has the id. Both documents are validated before either is written.

    The plan is written first. If the journal write then fails, confirming the
    same draft again finds the id already in the plan, leaves the plan as it
    is and writes only the journal entry, so a partial write can be completed.
    """
    journal = load_journal(owner, data_root)
    if journal.entry(body.id) is not None:
        raise DuplicateDecisionError(f"Decision {body.id} is already in the journal")
    current = load_plan(owner, data_root)
    in_plan = any(d.id == body.id for d in current.decisions)
    plan = None if in_plan else _plan_with_decision(current, body)
    entry = JournalEntry(
        id=body.id,
        date=body.date,
        kind=body.kind,
        source_ref=body.source_ref,
        amount_gbp=body.amount_gbp,
        legs=body.legs,
        expectation=body.expectation,
        snapshot=body.snapshot,
        review_due=review_due_dates(body.date),
    )
    journal.entries.append(entry)
    if plan is not None:
        save_plan(plan, data_root)
    save_journal(journal, data_root)
    return entry


def dismiss_change(owner: str, source_ref: str, data_root: Optional[Path] = None) -> None:
    """Stop listing ``source_ref`` as unlogged. Writes the journal only, never the plan."""
    journal = load_journal(owner, data_root)
    if source_ref not in journal.dismissed:
        journal.dismissed.append(source_ref)
        save_journal(journal, data_root)


def set_lesson(owner: str, entry_id: str, horizon_months: int, lesson: str, data_root: Optional[Path] = None) -> None:
    """Record the owner's lesson on one review. Raises ``LookupError`` when there is no such review."""
    journal = load_journal(owner, data_root)
    entry = journal.entry(entry_id)
    review = next((r for r in (entry.reviews if entry else []) if r.horizon_months == horizon_months), None)
    if review is None:
        raise LookupError(f"No {horizon_months}-month review for decision {entry_id}")
    review.lesson = lesson.strip() or None
    save_journal(journal, data_root)


def set_threshold(owner: str, threshold_gbp: float, data_root: Optional[Path] = None) -> None:
    journal = load_journal(owner, data_root)
    # A new settings object validates the value (attribute assignment would not).
    journal.settings = JournalSettings(threshold_gbp=threshold_gbp)
    save_journal(journal, data_root)
