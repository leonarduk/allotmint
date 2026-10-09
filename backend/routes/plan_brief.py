# backend/routes/plan_brief.py
"""Plan-drift briefs (#10475): run one on demand and read saved ones.

Access follows ``/plans/{owner}``: the owner must exist under the accounts root
and the caller must pass :func:`backend.common.authz.ensure_owner_access`, so a
brief is only visible to its owner. Briefs are stored beside that same accounts
root (``<accounts_root>/../plan_briefs``) unless ``PLAN_BRIEFS_URI`` is set.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from backend.auth import get_active_user
from backend.common.authz import ensure_owner_access
from backend.common.errors import raise_owner_not_found
from backend.common.investment_plan import PlanNotFoundError
from backend.config import config
from backend.plan_brief import store
from backend.plan_brief.service import run_brief
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory

router = APIRouter(tags=["plan-brief"])


def _resolve_owner(request: Request, owner: str, identity: Optional[str]) -> Tuple[str, Path]:
    """Canonical owner id and accounts root, after the owner-access check."""
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir is None:
        raise_owner_not_found(owner)
    assert owner_dir is not None  # raise_owner_not_found always raises; narrows the type for mypy
    ensure_owner_access(identity, owner_dir.name, accounts_root)
    return owner_dir.name, accounts_root


@router.post("/plan-brief/{owner}/run")
async def run_plan_brief(
    owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)
) -> Dict[str, Any]:
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        return await run_brief(owner, accounts_root, cfg=config, mcp_server_url=config.mcp_server_url)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"No portfolio found for {owner}") from exc
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Saved plan for {owner} is invalid: {exc}") from exc


@router.get("/plan-brief/{owner}/latest")
def get_latest_plan_brief(
    owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)
) -> Dict[str, Any]:
    owner, accounts_root = _resolve_owner(request, owner, identity)
    brief = store.latest_brief(owner, accounts_root.parent)
    if brief is None:
        raise HTTPException(status_code=404, detail=f"No plan brief saved for {owner}")
    return brief


@router.get("/plan-brief/{owner}")
def list_plan_briefs(
    owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)
) -> Dict[str, Any]:
    """Saved briefs, newest first, as summaries; ``/plan-brief/{owner}/{id}`` returns one in full."""
    owner, accounts_root = _resolve_owner(request, owner, identity)
    return {"owner": owner, "briefs": [store.brief_summary(b) for b in store.list_briefs(owner, accounts_root.parent)]}


@router.get("/plan-brief/{owner}/{brief_id}")
def get_plan_brief(
    owner: str, brief_id: str, request: Request, identity: Optional[str] = Depends(get_active_user)
) -> Dict[str, Any]:
    owner, accounts_root = _resolve_owner(request, owner, identity)
    for brief in store.list_briefs(owner, accounts_root.parent):
        if brief.get("id") == brief_id:
            return brief
    raise HTTPException(status_code=404, detail=f"No plan brief {brief_id} for {owner}")
