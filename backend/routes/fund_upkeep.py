"""Fund data upkeep bot endpoints (#10482).

* ``GET`` all-in cost / concentration / settings / proposals are page reads:
  cached prices only, no fetching, nothing stored.
* ``POST /fund-upkeep/{owner}/run`` is the explicit bot run (look-through
  refresh, concentration snapshot, OCF proposals). Until the #10477 bot
  registry exists this, or :func:`backend.fund_upkeep.bot.run`, is how it runs.
* Proposal approve/reject/undo: approval is the only path that writes agent
  findings, through the instrument-metadata admin update with an audit entry.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.common import group_portfolio
from backend.common import portfolio as portfolio_mod
from backend.common.authz import ensure_owner_access
from backend.common.errors import log_owner_not_found
from backend.common.portfolio_cache import cached_group_portfolio
from backend.config import config
from backend.fund_upkeep import bot, charges_agent, proposals
from backend.fund_upkeep.all_in_cost import compute_all_in_cost
from backend.routes import get_active_user
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory
from backend.routes.transactions import load_all_transactions, resolve_writable_store
from backend.timeseries.cache import cache_only

router = APIRouter(prefix="/fund-upkeep", tags=["fund-upkeep"])


class ThresholdsBody(BaseModel):
    thresholds: Dict[str, float]


class RunBody(BaseModel):
    use_agent: bool = True


def _authorised_owner(owner: str, request: Request, user: Optional[str]) -> str:
    """The owner's canonical (on-disk) name, after checking ``user`` may access it.

    Every owner route goes through this, so settings, snapshots and bot runs
    all key the same owner the same way whatever the URL's casing.
    """
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir:
        owner = owner_dir.name
    ensure_owner_access(user, owner, accounts_root)
    return owner


def _owner_portfolio(owner: str, request: Request, user: Optional[str]) -> tuple[str, Dict[str, Any]]:
    owner = _authorised_owner(owner, request, user)
    accounts_root = resolve_accounts_root(request)
    try:
        return owner, portfolio_mod.build_owner_portfolio(owner, accounts_root)
    except FileNotFoundError as exc:
        log_owner_not_found(owner)
        raise HTTPException(status_code=404, detail="Owner not found") from exc


def _transactions(request: Request, owners: set[str]) -> List[Dict[str, Any]]:
    store, _ = resolve_writable_store(request)
    return [t.model_dump() for t in load_all_transactions(store) if t.owner.lower() in owners]


@router.get("/{owner}/all-in-cost")
def owner_all_in_cost(owner: str, request: Request, user: Optional[str] = Depends(get_active_user)):
    """Fund charges plus 12 months of fees, per account and in total, with unknowns kept apart."""
    owner, portfolio = _owner_portfolio(owner, request, user)
    with cache_only():
        return compute_all_in_cost(portfolio, _transactions(request, {owner.lower()}))


@router.get("/group/{slug}/all-in-cost")
def group_all_in_cost(slug: str, request: Request):
    """All-in cost of a group portfolio.

    Same access as every ``/portfolio-group/{slug}/*`` route (including the
    full group holdings at ``/portfolio-group/{slug}``): any authenticated
    user, via the router-level auth dependency. The app has no per-group
    membership check yet; adding one belongs on all group routes together.
    """
    try:
        portfolio = cached_group_portfolio(slug, None, lambda: group_portfolio.build_group_portfolio(slug))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc
    owners = {str(a.get("owner") or "").lower() for a in portfolio.get("accounts") or []}
    with cache_only():
        return compute_all_in_cost(portfolio, _transactions(request, owners))


@router.get("/{owner}/concentration")
def owner_concentration(owner: str, request: Request, user: Optional[str] = Depends(get_active_user)):
    """Concentration alerts against the owner's thresholds and the last bot run (read-only)."""
    owner, portfolio = _owner_portfolio(owner, request, user)
    return bot.concentration_for(owner, portfolio)


@router.get("/{owner}/settings")
def get_settings(owner: str, request: Request, user: Optional[str] = Depends(get_active_user)):
    return bot.get_settings(_authorised_owner(owner, request, user))


@router.put("/{owner}/settings")
def put_settings(owner: str, body: ThresholdsBody, request: Request, user: Optional[str] = Depends(get_active_user)):
    return bot.save_settings(_authorised_owner(owner, request, user), body.thresholds)


@router.post("/{owner}/run")
def run_bot(
    owner: str, request: Request, body: Optional[RunBody] = None, user: Optional[str] = Depends(get_active_user)
):
    """Run the upkeep bot now. Offline mode skips every network step."""
    owner, portfolio = _owner_portfolio(owner, request, user)
    fetch = not config.offline_mode
    llm = charges_agent.openai_compat_step(config) if fetch and (body is None or body.use_agent) else None
    return bot.run(
        owner=owner, portfolio=portfolio, transactions=_transactions(request, {owner.lower()}), llm=llm, fetch=fetch
    )


@router.get("/proposals")
def list_proposals(status: Optional[str] = Query(None, pattern="^(pending|approved|rejected|undone)$")):
    return proposals.list_proposals(status)


# Fixed texts: responses never carry exception text (CodeQL py/stack-trace-exposure).
_STATE_DETAIL = "The proposal is not in a state that allows this action"
_CONFLICT_DETAIL: Dict[type, str] = {
    proposals.ProposalConflict: "The metadata has changed since this approval; edit it directly instead",
}


def _decide(action, proposal_id: str, user: Optional[str]) -> Dict[str, Any]:
    try:
        return action(proposal_id, actor=user)
    except proposals.ProposalNotFound as exc:
        raise HTTPException(status_code=404, detail="Proposal not found") from exc
    except (proposals.ProposalStateError, proposals.ProposalConflict) as exc:
        raise HTTPException(status_code=409, detail=_CONFLICT_DETAIL.get(type(exc), _STATE_DETAIL)) from exc


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: str, user: Optional[str] = Depends(get_active_user)):
    """Write the proposed value to instrument metadata, with an audit entry."""
    return _decide(proposals.approve, proposal_id, user)


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: str, user: Optional[str] = Depends(get_active_user)):
    return _decide(proposals.reject, proposal_id, user)


@router.post("/proposals/{proposal_id}/undo")
def undo_proposal(proposal_id: str, user: Optional[str] = Depends(get_active_user)):
    """Restore the values an approval replaced (audited)."""
    return _decide(proposals.undo, proposal_id, user)
