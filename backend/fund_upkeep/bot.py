"""One run of the fund data upkeep bot (#10482).

:func:`run` is a standalone entry point returning a JSON-ready summary; a
scheduler (the #10477 bot registry, monthly, once it exists) or
``POST /fund-upkeep/{owner}/run`` calls it. A run:

1. refreshes stale look-through blocks for held funds (``max_age_days``);
2. reports concentration against the owner's thresholds and the previous
   run, then stores this run's snapshot for the next comparison;
3. totals the all-in annual cost;
4. asks the OCF agent about held funds with a missing or stale charge and
   queues its sourced proposals for approval -- it never writes them;
5. asks the look-through agent (:mod:`.look_through_agent`, #10492) about
   held funds step 1 left unresolved for want of a source, and queues its
   sourced ``look_through`` proposals the same way. Fresh funds are never
   in that list, so they are not refetched.

Page reads (``GET`` routes) use the deterministic parts only and never fetch
or store anything.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from backend.common.look_through import DEFAULT_MAX_AGE_DAYS, compute_look_through
from backend.fund_upkeep import charges_agent, look_through_agent, look_through_upkeep, proposals, storage
from backend.fund_upkeep.all_in_cost import compute_all_in_cost
from backend.fund_upkeep.concentration import concentration_alerts, normalise_thresholds, snapshot
from backend.timeseries.cache import cache_only

SETTINGS_FILE = "settings.json"
SNAPSHOTS_FILE = "snapshots.json"
DEFAULT_MAX_AGENT_FUNDS = 10


def _owner_key(owner: str) -> str:
    return owner.strip().lower()


def get_settings(owner: str) -> Dict[str, Any]:
    stored = storage.read_json(SETTINGS_FILE, {})
    entry = stored.get(_owner_key(owner)) if isinstance(stored, dict) else None
    return {"thresholds": normalise_thresholds((entry or {}).get("thresholds"))}


def save_settings(owner: str, thresholds: Mapping[str, Any]) -> Dict[str, Any]:
    clean = normalise_thresholds(thresholds)
    with storage.LOCK:
        stored = storage.read_json(SETTINGS_FILE, {})
        stored = stored if isinstance(stored, dict) else {}
        stored[_owner_key(owner)] = {"thresholds": clean}
        storage.write_json(SETTINGS_FILE, stored)
    return {"thresholds": clean}


def previous_snapshot(owner: str) -> Optional[Dict[str, Any]]:
    stored = storage.read_json(SNAPSHOTS_FILE, {})
    entry = stored.get(_owner_key(owner)) if isinstance(stored, dict) else None
    return entry.get("snapshot") if isinstance(entry, dict) else None


def _save_snapshot(owner: str, data: Dict[str, Any]) -> None:
    with storage.LOCK:
        stored = storage.read_json(SNAPSHOTS_FILE, {})
        stored = stored if isinstance(stored, dict) else {}
        stored[_owner_key(owner)] = {"taken_at": datetime.now(timezone.utc).isoformat(), "snapshot": data}
        storage.write_json(SNAPSHOTS_FILE, stored)


def concentration_for(owner: str, portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """Read-only concentration report (no snapshot is stored)."""
    with cache_only():
        exposure = compute_look_through(portfolio)
    return concentration_alerts(exposure, get_settings(owner)["thresholds"], previous_snapshot(owner))


# propose_charge / propose_look_through: (fund, *, llm, toolbox, today) -> outcome.
Proposer = Callable[..., Dict[str, Any]]


def _queue_proposals(
    funds: List[Dict[str, Any]],
    propose: Proposer,
    *,
    today: date,
    llm: charges_agent.LlmStep,
    toolbox: charges_agent.ReadOnlyToolbox,
) -> List[Dict[str, Any]]:
    """Run an agent per fund and queue each validated proposal for approval (never written here)."""
    results = []
    for fund in funds:
        outcome = propose(fund, llm=llm, toolbox=toolbox, today=today)
        if outcome["status"] == "proposed":
            queued = proposals.add_proposal(outcome["proposal"])
            outcome = {"status": "queued", "proposal_id": queued["id"]} if queued else {"status": "already_pending"}
        results.append({"ticker": fund["ticker"], **outcome})
    return results


def _without_source(funds: List[Dict[str, Any]], look_through: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Funds the scrapers looked for and could not resolve (not missing-ISIN or failed requests)."""
    unresolved = look_through.get("unresolved") or []
    tickers = {item["ticker"] for item in unresolved if item.get("reason") == "no source"}
    return [fund for fund in funds if fund["ticker"] in tickers]


def _agent_step(
    funds: List[Dict[str, Any]],
    propose: Proposer,
    *,
    fetch: bool,
    llm: Optional[charges_agent.LlmStep],
    toolbox: Optional[charges_agent.ReadOnlyToolbox],
    today: date,
    limit: int,
) -> Any:
    """Queue an agent's proposals for up to ``limit`` funds, or say why the step was skipped."""
    if not fetch or llm is None or toolbox is None:
        return {"skipped": "offline" if not fetch else "no LLM configured", "funds": [f["ticker"] for f in funds]}
    return _queue_proposals(funds[:limit], propose, today=today, llm=llm, toolbox=toolbox)


def run(
    *,
    owner: str,
    portfolio: Dict[str, Any],
    transactions: Iterable[Mapping[str, Any]],
    today: Optional[date] = None,
    llm: Optional[charges_agent.LlmStep] = None,
    toolbox: Optional[charges_agent.ReadOnlyToolbox] = None,
    fetch: bool = True,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    max_agent_funds: int = DEFAULT_MAX_AGENT_FUNDS,
    refresh_kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run every upkeep step for ``owner``; ``fetch=False`` (offline) skips network steps."""
    day = today or date.today()
    funds = look_through_upkeep.held_funds(portfolio)
    look_through = (
        look_through_upkeep.refresh_stale(funds, today=day, max_age_days=max_age_days, **(refresh_kwargs or {}))
        if fetch
        else {"skipped": "offline"}
    )
    with cache_only():
        exposure = compute_look_through(portfolio)
    concentration = concentration_alerts(exposure, get_settings(owner)["thresholds"], previous_snapshot(owner))
    _save_snapshot(owner, snapshot(exposure))
    needing = [f for f in funds if charges_agent.needs_charge(f["meta"], day)]
    tools = (toolbox or charges_agent.ReadOnlyToolbox()) if fetch and llm is not None else None
    charges = _agent_step(
        needing, charges_agent.propose_charge, llm=llm, toolbox=tools, today=day, limit=max_agent_funds, fetch=fetch
    )
    look_through_proposals = _agent_step(
        _without_source(funds, look_through),
        look_through_agent.propose_look_through,
        llm=llm,
        toolbox=tools,
        today=day,
        limit=max_agent_funds,
        fetch=fetch,
    )
    return {
        "owner": owner,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "look_through": look_through,
        "concentration": concentration,
        "all_in_cost": compute_all_in_cost(portfolio, transactions, today=day),
        "ongoing_charges": charges,
        "look_through_proposals": look_through_proposals,
        "pending_proposals": len(proposals.list_proposals("pending")),
    }
