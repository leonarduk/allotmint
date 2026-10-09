"""Cash deployment tracker bot entry point (#10480).

:func:`run` is the standalone ``run(owner, as_of) -> dict`` the #10477 bot
registry can wrap once it exists. It is read-only: for each of the owner's
schedules it checks progress against the account's transactions and, for an
active schedule with a tranche due now, drafts that tranche's order list from
the owner's plan. It never writes, never proposes a schedule and never trades.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

from backend.cash_deployment.progress import build_progress
from backend.cash_deployment.schedule import DeploymentSchedule, list_schedules
from backend.cash_deployment.tranche import PriceLookup, build_tranche, default_prices, target_policy
from backend.common import portfolio as portfolio_mod
from backend.common.allocation_policy import AllocationPolicy, load_allocation_policy
from backend.common.data_loader import resolve_default_accounts_root, resolve_owner_dir
from backend.common.investment_plan import InvestmentPlan, PlanNotFoundError, load_plan
from backend.common.sleeves import SleeveSetup, load_sleeves
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

BOT_ID = "cash_deployment"
BOT_NAME = "Cash deployment tracker"
BOT_DESCRIPTION = "Tracks your own cash phasing schedule: tranches due, order list per your plan, and progress."
TRANSACTIONS_SUFFIX = "_transactions.json"


def load_account_transactions(owner: str, account: str, accounts_root: Optional[Path]) -> list[dict[str, Any]]:
    """Rows of ``owner``'s ``<account>_transactions.json`` only (case-insensitive); ``[]`` when absent."""
    owner_dir = resolve_owner_dir(owner, accounts_root)
    wanted = f"{account}{TRANSACTIONS_SUFFIX}".lower()
    for path in owner_dir.glob(f"*{TRANSACTIONS_SUFFIX}"):
        if path.name.lower() == wanted:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError(f"Transactions for account {account!r} are unreadable: {exc}") from exc
            rows = data.get("transactions") if isinstance(data, dict) else None
            return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    return []


@dataclass
class OwnerContext:
    """Lazily loaded owner data shared by every schedule in one run."""

    owner: str
    accounts_root: Path
    prices: PriceLookup = default_prices
    warnings: list[str] = field(default_factory=list)

    @cached_property
    def portfolio(self) -> dict[str, Any]:
        return portfolio_mod.build_owner_portfolio(self.owner, self.accounts_root, include_account_stem=True)

    @cached_property
    def policy(self) -> AllocationPolicy:
        return load_allocation_policy(self.owner, self.accounts_root)

    @cached_property
    def setup(self) -> SleeveSetup:
        return load_sleeves(self.owner, self.accounts_root)

    @cached_property
    def plan(self) -> Optional[InvestmentPlan]:
        try:
            return load_plan(self.owner, self.accounts_root.parent)
        except PlanNotFoundError:
            return None
        except (ValidationError, ValueError) as exc:
            logger.warning("Ignoring invalid plan for %s: %s", sanitise_log_value(self.owner), sanitise_log_value(exc))
            self.warnings.append(f"Your saved investment plan is invalid, so no vehicles are suggested: {exc}")
            return None


def _tranche(schedule: DeploymentSchedule, ctx: OwnerContext, current: dict[str, Any]) -> dict[str, Any]:
    policy = target_policy(schedule.target_source, ctx.policy, ctx.plan)
    remaining = current["amount_minor"] - current["invested_minor"]
    tranche = build_tranche(ctx.portfolio, policy, ctx.setup, ctx.plan, schedule.account, remaining, ctx.prices)
    return {**tranche, "index": current["index"], "due_date": current["due_date"]}


def evaluate_schedule(schedule: DeploymentSchedule, ctx: OwnerContext, as_of: date) -> dict[str, Any]:
    """Progress for one schedule plus, when active and a tranche is due, its draft order list."""
    result: dict[str, Any] = {"schedule": schedule.to_dict(), "progress": None, "tranche": None, "error": None}
    try:
        transactions = load_account_transactions(ctx.owner, schedule.account, ctx.accounts_root)
        result["progress"] = build_progress(schedule, transactions, as_of)
        current = result["progress"]["current"]
        if schedule.status == "active" and current is not None:
            result["tranche"] = _tranche(schedule, ctx, current)
    except ValueError as exc:
        result["error"] = str(exc)
    return result


def _run_summary(results: list[dict[str, Any]]) -> str:
    due = sum(1 for r in results if r["tranche"] is not None)
    overdue = sum(r["progress"]["overdue_count"] for r in results if r["progress"])
    count = len(results)
    return f"{due} tranche(s) due now, {overdue} overdue across {count} schedule(s)"


def _run_status(results: list[dict[str, Any]]) -> str:
    if not any(r["schedule"]["status"] == "active" for r in results):
        return "skipped"
    return "partial" if any(r["error"] for r in results) else "ok"


def run(
    owner: str,
    as_of: Optional[date] = None,
    *,
    accounts_root: Optional[Path] = None,
    prices: PriceLookup = default_prices,
) -> dict[str, Any]:
    """One read-only bot run for ``owner`` on ``as_of`` (default today)."""
    as_of = as_of or date.today()
    ctx = OwnerContext(owner, Path(accounts_root) if accounts_root else resolve_default_accounts_root(), prices)
    results = [evaluate_schedule(s, ctx, as_of) for s in list_schedules(owner, ctx.accounts_root)]
    return {
        "bot": BOT_ID,
        "name": BOT_NAME,
        "owner": owner,
        "as_of": as_of.isoformat(),
        "status": _run_status(results),
        "summary": _run_summary(results),
        "schedules": results,
        "warnings": ctx.warnings,
    }
