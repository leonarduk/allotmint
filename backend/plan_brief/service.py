"""Build, check and save one owner's plan-drift brief (#10475).

Shared by ``POST /plan-brief/{owner}/run`` and the monthly Lambda
(:mod:`backend.lambda_api.plan_brief`). It only reads the plan, allocation
policy, portfolio and transactions; its only write is the brief itself
(:func:`backend.plan_brief.store.save_brief`).
"""

from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path
from typing import Any, Optional

from backend.common import portfolio as portfolio_mod
from backend.common.allocation_policy import load_allocation_policy
from backend.common.investment_plan import load_plan
from backend.plan_brief import store
from backend.plan_brief.agent import ChatTurn, run_agent
from backend.plan_brief.drift import build_facts, load_owner_transactions

BRIEF_SCHEMA_VERSION = 1


async def run_brief(
    owner: str,
    accounts_root: Path,
    *,
    cfg: Any,
    mcp_server_url: Optional[str],
    today: Optional[dt.date] = None,
    chat_turn: Optional[ChatTurn] = None,
    save: bool = True,
) -> dict[str, Any]:
    """Generate ``owner``'s brief and (by default) save it; returns the brief.

    Raises :class:`~backend.common.investment_plan.PlanNotFoundError` without a
    plan and ``FileNotFoundError`` without a portfolio.
    """
    today = today or dt.date.today()
    data_root = Path(accounts_root).parent
    plan = load_plan(owner, data_root)
    policy = load_allocation_policy(owner, accounts_root)
    portfolio = portfolio_mod.build_owner_portfolio(owner, accounts_root, include_account_stem=True)
    transactions = load_owner_transactions(accounts_root, owner)
    # "What changed" compares with the last brief from an earlier day, so a
    # second run on the same day doesn't report an empty window.
    previous = next((b for b in store.list_briefs(owner, data_root) if str(b.get("as_of")) < today.isoformat()), None)
    facts = build_facts(plan, portfolio, policy, transactions, today, previous)

    narrative = await run_agent(
        plan, facts, today=today.isoformat(), cfg=cfg, mcp_server_url=mcp_server_url, chat_turn=chat_turn
    )
    brief = {
        "schema_version": BRIEF_SCHEMA_VERSION,
        "id": uuid.uuid4().hex,
        "owner": owner,
        "as_of": today.isoformat(),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "plan_version": plan.version,
        "plan_updated": plan.updated.isoformat(),
        **facts,
        **narrative,
        # Always shown with the brief, whatever the agent wrote.
        "disclaimer": plan.disclaimer,
    }
    if save:
        store.save_brief(owner, brief, data_root)
    return brief
