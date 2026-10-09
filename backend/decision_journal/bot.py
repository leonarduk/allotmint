"""Daily decision-journal run (#10481).

Standalone until the bot registry (#10477) exists: :func:`run` finds
qualifying trades not yet logged or dismissed and runs the reviews that have
fallen due, returning a JSON-ready summary. It writes reviews to the journal's
sidecar store only; it never writes the plan, and it never logs a decision on
the owner's behalf (unlogged changes are only listed).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from backend.common.investment_plan import plans_dir
from backend.decision_journal.capture import lookback_window, qualifying_trades
from backend.decision_journal.prices import SeriesLoader, load_return_series
from backend.decision_journal.review import run_due_reviews
from backend.decision_journal.store import journal_dir, load_journal, save_journal

BOT_ID = "decision_journal"
BOT_NAME = "Decision journal"
BOT_SCHEDULE = "daily"


def known_owners(data_root: Optional[Path] = None) -> list[str]:
    """Owners with a saved plan or journal."""
    stems = set()
    for directory in (plans_dir(data_root), journal_dir(data_root)):
        if directory.is_dir():
            stems |= {path.stem for path in directory.glob("*.json")}
    return sorted(stems)


def _all_transactions() -> list[Mapping[str, Any]]:
    from backend.routes.transactions import load_all_transactions

    return [tx.model_dump() for tx in load_all_transactions()]


def run_for_owner(
    owner: str,
    transactions: Iterable[Mapping[str, Any]],
    *,
    as_of: date,
    data_root: Optional[Path] = None,
    load_series: SeriesLoader = load_return_series,
) -> dict[str, Any]:
    journal = load_journal(owner, data_root)
    since, until = lookback_window(as_of)
    owned = [tx for tx in transactions if str(tx.get("owner") or "").lower() == owner.lower()]
    unlogged = qualifying_trades(
        owned,
        threshold_gbp=journal.settings.threshold_gbp,
        handled_refs=journal.handled_refs(),
        since=since,
        until=until,
    )
    added = run_due_reviews(journal, as_of, load_series)
    if added:
        save_journal(journal, data_root)
    return {
        "unlogged": unlogged,
        "reviews_run": [{"entry_id": entry_id, "horizon_months": r.horizon_months} for entry_id, r in added],
    }


def run(
    owners: Optional[Iterable[str]] = None,
    *,
    as_of: Optional[date] = None,
    data_root: Optional[Path] = None,
    transactions: Optional[Iterable[Mapping[str, Any]]] = None,
    load_series: SeriesLoader = load_return_series,
) -> dict[str, Any]:
    """One daily pass over ``owners`` (default: everyone with a plan or journal)."""
    day = as_of or date.today()
    txs = list(_all_transactions() if transactions is None else transactions)
    results = {
        owner: run_for_owner(owner, txs, as_of=day, data_root=data_root, load_series=load_series)
        for owner in (known_owners(data_root) if owners is None else owners)
    }
    return {"bot": BOT_ID, "name": BOT_NAME, "schedule": BOT_SCHEDULE, "as_of": day.isoformat(), "owners": results}
