"""Expected-vs-actual contribution matching (#10479). Deterministic; no LLM.

Each expected contribution from the owner's schedule is matched against the
account's DEPOSIT rows within a window around the expected date:

- ``on_time``: matched, paid at most :data:`ON_TIME_GRACE_DAYS` after the expected day
  (or up to :data:`EARLY_DAYS` before it);
- ``late``: matched, paid later than that but within :data:`LATE_WINDOW_DAYS`;
- ``wrong_amount``: a payment arrived in the window but neither it nor the window's
  payments together match the expected amount;
- ``missing``: nothing arrived and the window has closed;
- ``awaiting``: nothing matching yet, but the window is still open.

A split payment (several rows in the window that add up to the amount) counts as a
match. Relief-at-source top-ups, transfers, refunds and reversals are never matched: the schedule
records the amount the owner pays, and the relief arrives separately weeks later.
Each row is used at most once. Amounts are pence (``amount_minor``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from backend.allowance_guardian.schedule import ScheduledContribution, expected_dates

EARLY_DAYS = 5
ON_TIME_GRACE_DAYS = 2
LATE_WINDOW_DAYS = 14
AMOUNT_TOLERANCE_MINOR = 100

# Whole-word comment tags marking an employer or salary-sacrifice DEPOSIT. Mirrors
# allotmint_pro.mcp_server.transaction_summary.EMPLOYER_COMMENT_TAGS, which decides
# what counts towards the annual allowance; kept here so matching works without it.
EMPLOYER_COMMENT_TAGS = ("employer", "salary sacrifice", "salary exchange")
_EMPLOYER_TAG_RE = re.compile(r"\b(?:" + "|".join(EMPLOYER_COMMENT_TAGS) + r")\b")
# Relief top-ups, transfers, refunds, reversals, repayments and corrections are not
# contributions the owner scheduled, so they are never matched.
_NEVER_MATCHED_RE = re.compile(r"tax relief|\b(?:transfer|refund|revers|repay|correction)")

STATUSES = ("on_time", "late", "wrong_amount", "missing", "awaiting")


@dataclass(frozen=True)
class Deposit:
    """A money-in row eligible for matching."""

    id: str
    account: str
    date: date
    amount_minor: int
    employer: bool


def _as_deposit(tx: Any) -> Optional[Deposit]:
    if (tx.type or "").strip().upper() != "DEPOSIT" or tx.amount_minor is None or not tx.date:
        return None
    if (tx.currency or "GBP").strip().upper() != "GBP":
        return None
    comment = (tx.comments or "").lower()
    if _NEVER_MATCHED_RE.search(comment):
        return None
    return Deposit(
        id=str(tx.id or f"{tx.account}:{tx.date}:{tx.amount_minor}"),
        account=(tx.account or "").lower(),
        date=date.fromisoformat(str(tx.date)[:10]),
        amount_minor=abs(int(round(tx.amount_minor))),
        employer=bool(_EMPLOYER_TAG_RE.search(comment)),
    )


def deposits_from_transactions(transactions: Iterable[Any]) -> List[Deposit]:
    """Matchable DEPOSIT rows from ``Transaction``-like rows, oldest first."""
    found = [dep for dep in (_as_deposit(tx) for tx in transactions) if dep is not None]
    return sorted(found, key=lambda dep: (dep.date, dep.id))


def _eligible(dep: Deposit, item: ScheduledContribution) -> bool:
    if dep.account != item.account.lower():
        return False
    if item.source == "isa_subscription":
        return True
    return dep.employer == (item.source == "employer")


def _close(amount: int, expected: int) -> bool:
    return abs(amount - expected) <= AMOUNT_TOLERANCE_MINOR


def _pick(candidates: Sequence[Deposit], due: date, expected: int) -> tuple[List[Deposit], bool]:
    """Rows paying ``expected`` (one row, else a date-ordered split); else the nearest row, unmatched."""
    exact = [dep for dep in candidates if _close(dep.amount_minor, expected)]
    if exact:
        return [min(exact, key=lambda dep: (abs((dep.date - due).days), dep.date))], True
    running: List[Deposit] = []
    for dep in candidates:
        running.append(dep)
        if _close(sum(d.amount_minor for d in running), expected):
            return running, True
    return [min(candidates, key=lambda dep: (abs((dep.date - due).days), dep.date))], False


def _result(item: ScheduledContribution, due: date, status: str, rows: Sequence[Deposit]) -> Dict[str, Any]:
    received = sum(dep.amount_minor for dep in rows)
    return {
        "account": item.account,
        "source": item.source,
        "label": item.label,
        "expected_date": due.isoformat(),
        "expected_amount_minor": item.amount_minor,
        "status": status,
        "received_amount_minor": received if rows else None,
        "difference_minor": received - item.amount_minor if rows else None,
        "days_late": max((rows[-1].date - due).days, 0) if rows else None,
        "matched_rows": [{"id": d.id, "date": d.date.isoformat(), "amount_minor": d.amount_minor} for d in rows],
    }


def _match_one(
    item: ScheduledContribution, due: date, deposits: Sequence[Deposit], used: Set[str], today: date
) -> Dict[str, Any]:
    window_start, window_end = due - timedelta(days=EARLY_DAYS), due + timedelta(days=LATE_WINDOW_DAYS)
    candidates = [
        dep
        for dep in deposits
        if dep.id not in used and window_start <= dep.date <= min(window_end, today) and _eligible(dep, item)
    ]
    if not candidates:
        return _result(item, due, "missing" if today > window_end else "awaiting", [])
    rows, matched = _pick(candidates, due, item.amount_minor)
    if not matched and today <= window_end:
        # The rest of a split payment may still arrive; leave the rows free until the window closes.
        return _result(item, due, "awaiting", rows)
    used.update(dep.id for dep in rows)
    if not matched:
        return _result(item, due, "wrong_amount", rows)
    on_time = (rows[-1].date - due).days <= ON_TIME_GRACE_DAYS
    return _result(item, due, "on_time" if on_time else "late", rows)


def match_contributions(
    schedule: Sequence[ScheduledContribution], transactions: Iterable[Any], since: date, today: date
) -> Dict[str, Any]:
    """Check every contribution expected in ``[since, today]`` against ``transactions``.

    ``transactions`` are one owner's ``Transaction``-like rows. Returns
    ``{"results": [...], "counts": {status: n}, "unmatched_deposits": [...]}``;
    results are in expected-date order and ``unmatched_deposits`` lists deposits
    in scheduled accounts since ``since`` that no expected contribution used.
    """
    deposits = deposits_from_transactions(transactions)
    due_list = sorted(
        ((due, idx) for idx, item in enumerate(schedule) for due in expected_dates(item, since, today)),
    )
    used: Set[str] = set()
    results = [_match_one(schedule[idx], due, deposits, used, today) for due, idx in due_list]
    accounts = {item.account.lower() for item in schedule}
    unmatched = [
        {"id": d.id, "account": d.account, "date": d.date.isoformat(), "amount_minor": d.amount_minor}
        for d in deposits
        if d.account in accounts and d.date >= since and d.id not in used
    ]
    counts = {status: sum(1 for r in results if r["status"] == status) for status in STATUSES}
    return {"results": results, "counts": counts, "unmatched_deposits": unmatched}
