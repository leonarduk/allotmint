# backend/routes/rebalance.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.auth import get_active_user
from backend.common import portfolio as portfolio_mod
from backend.common.allocation_policy import (
    SettingsUnreadableError,
    load_allocation_policy,
    parse_policy,
    save_allocation_policy,
)
from backend.common.authz import ensure_owner_access
from backend.common.errors import raise_owner_not_found
from backend.common.sleeve_plan import build_sleeved_plan, sleeve_new_cash
from backend.common.sleeves import CORE_ID, load_sleeves
from backend.common.strategies import active_strategy
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory

router = APIRouter(tags=["rebalance"])


class AllocationPolicyBody(BaseModel):
    targets: Dict[str, float] = {}
    tolerance_pct: Optional[float] = None


def _resolve_owner(request: Request, owner: str, identity: Optional[str]) -> Tuple[str, Path]:
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir is None:
        raise_owner_not_found(owner)
    ensure_owner_access(identity, owner_dir.name, accounts_root)
    return owner_dir.name, accounts_root


def _load_portfolio(owner: str, accounts_root: Path) -> Dict[str, Any]:
    try:
        # Stems give each account a stable id across the plan/new-cash requests (#9496).
        return portfolio_mod.build_owner_portfolio(owner, accounts_root, include_account_stem=True)
    except FileNotFoundError:
        raise_owner_not_found(owner)


@router.get("/rebalance/{owner}/policy")
def get_policy(owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    return load_allocation_policy(owner, accounts_root).to_dict()


@router.put("/rebalance/{owner}/policy")
def put_policy(
    owner: str,
    body: AllocationPolicyBody,
    request: Request,
    identity: Optional[str] = Depends(get_active_user),
):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    data = body.model_dump(exclude_none=True)
    try:
        policy = parse_policy(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        save_allocation_policy(owner, policy, accounts_root)
    except SettingsUnreadableError as exc:
        raise HTTPException(
            status_code=409, detail="Owner settings file is unreadable; fix or remove it before saving targets"
        ) from exc
    return policy.to_dict()


@router.get("/rebalance/{owner}/plan")
def get_plan(owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    policy = load_allocation_policy(owner, accounts_root)
    setup = load_sleeves(owner, accounts_root)
    core_strategy = active_strategy(owner, accounts_root) if setup.sleeves else None
    return build_sleeved_plan(_load_portfolio(owner, accounts_root), policy, setup, core_strategy)


@router.get("/rebalance/{owner}/new-cash")
def get_new_cash_plan(
    owner: str,
    amount: float,
    account: str,
    request: Request,
    sleeve: str = CORE_ID,
    identity: Optional[str] = Depends(get_active_user),
):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    policy = load_allocation_policy(owner, accounts_root)
    setup = load_sleeves(owner, accounts_root)
    try:
        return sleeve_new_cash(_load_portfolio(owner, accounts_root), policy, setup, sleeve, amount, account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
