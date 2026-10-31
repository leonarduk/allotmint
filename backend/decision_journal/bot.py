"""Daily decision-journal run (#10481), registered as a bot (#10477).

:func:`run` finds qualifying trades not yet logged or dismissed and runs the
reviews that have fallen due, returning a JSON-ready summary. It writes
reviews to the journal's sidecar store only; it never writes the plan, and it
never logs a decision on the owner's behalf (unlogged changes are only
listed). :class:`DecisionJournalBot` puts it on the Bots page.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from backend.bots.registry import BotKind, BotRunContext, BotScope, BotSettings, RunResult, Schedule, register_bot
from backend.common.data_providers import DATA_BUCKET_ENV
from backend.common.investment_plan import plan_owners
from backend.config import config
from backend.decision_journal.capture import lookback_window, qualifying_trades
from backend.decision_journal.prices import SeriesLoader, load_return_series
from backend.decision_journal.review import run_due_reviews
from backend.decision_journal.store import journal_owners, load_journal, save_journal

BOT_ID = "decision-journal"
BOT_NAME = "Decision journal"
BOT_SCHEDULE = "daily"


def known_owners(data_root: Optional[Path] = None) -> list[str]:
    """Owners with a saved plan or journal (S3 prefixes on AWS, local directories otherwise)."""
    return sorted(plan_owners(data_root) | journal_owners(data_root))


def _all_transactions() -> list[Mapping[str, Any]]:
    """Every owner's transactions, including the writable store on AWS.

    On AWS ``config.accounts_root`` is the empty ``/tmp/data/accounts``, so the
    owners' own transactions are only in ``S3AccountsStore`` (writable-accounts/),
    resolved as in ``backend.common.dividends._resolve_store``.
    """
    from backend.routes.transactions import load_all_transactions

    store = None
    bucket = os.getenv(DATA_BUCKET_ENV)
    if config.app_env == "aws" and bucket:
        from backend.common.accounts_store import S3AccountsStore

        store = S3AccountsStore(bucket=bucket)
    return [tx.model_dump() for tx in load_all_transactions(store)]


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


def _counts(result: Mapping[str, Any]) -> dict[str, int]:
    """Totals across owners; the Bots page shows reports to every signed-in user, so no owner names."""
    owners = result["owners"].values()
    return {
        "owners": len(result["owners"]),
        "unlogged": sum(len(o["unlogged"]) for o in owners),
        "reviews_run": sum(len(o["reviews_run"]) for o in owners),
    }


class DecisionJournalBot:
    id = BOT_ID
    name = BOT_NAME
    description = (
        "Lists qualifying trades not yet logged in the decision journal and runs the 6- and 12-month "
        "reviews that have fallen due. Never writes the plan."
    )
    kind: BotKind = "rules"
    scope: BotScope = "system"
    settings_model: type[BotSettings] = BotSettings
    # No EventBridge rule or Lambda yet: it runs from the Bots page's Run now (locally)
    # and POST /decision-journal/{owner}/run.
    default_schedule: Optional[Schedule] = None
    timeout_minutes = 15

    def default_settings(self) -> dict[str, Any]:
        return {"enabled": True, "cadence": BOT_SCHEDULE}

    def run(self, context: BotRunContext, settings: BotSettings) -> RunResult:
        result = run(as_of=context.started_at.date())
        counts = _counts(result)
        summary = (
            f"{counts['unlogged']} unlogged trade{'s' if counts['unlogged'] != 1 else ''}, "
            f"{counts['reviews_run']} review{'s' if counts['reviews_run'] != 1 else ''} run "
            f"across {counts['owners']} owner{'s' if counts['owners'] != 1 else ''}"
        )
        return RunResult(status="ok", summary=summary, report=counts, raw=result)


register_bot(DecisionJournalBot(), replace=True)
