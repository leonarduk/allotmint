# backend/routes/strategies.py
"""Owner-scoped strategy library for the strategy page (#9653).

Built-in strategies are read-only: update and delete answer 403 and point at
duplicate. Access follows the other ``/{owner}`` routes (e.g.
``/rebalance/{owner}``): the owner must exist under the request's accounts
root and the caller must pass :func:`backend.common.authz.ensure_owner_access`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.auth import get_active_user
from backend.common.authz import ensure_owner_access
from backend.common.errors import raise_owner_not_found
from backend.common.settings_file import SettingsUnreadableError
from backend.common.strategies import (
    BuiltinStrategyError,
    StrategyNotFoundError,
    active_strategy,
    apply_strategy,
    create_strategy,
    delete_strategy,
    duplicate_strategy,
    get_strategy,
    list_strategies,
    update_strategy,
)
from backend.common.strategy_stress import stress_strategies
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory
from backend.routes.scenario import parse_horizons, resolve_event

router = APIRouter(tags=["strategies"])

UNREADABLE_DETAIL = "Owner settings file is unreadable; fix or remove it before saving strategies"


class StrategyBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    targets: Optional[Dict[str, float]] = None


class DuplicateBody(BaseModel):
    name: Optional[str] = None


DEFAULT_STRESS_HORIZONS = ("1m", "3m", "1y")
MAX_STRESS_HORIZONS = 6
MAX_STRESS_HORIZON_DAYS = 3650


class StressBody(BaseModel):
    event_id: Optional[str] = None
    date: Optional[str] = None
    horizons: List[str] = Field(default_factory=lambda: list(DEFAULT_STRESS_HORIZONS))


def _stress_horizons(raw: List[str]) -> Dict[str, int]:
    """Parse horizons as ``/scenario/historical`` does, within 1 day to 10 years and at most six."""
    horizons = parse_horizons(raw)
    if len(horizons) > MAX_STRESS_HORIZONS:
        raise HTTPException(status_code=400, detail=f"at most {MAX_STRESS_HORIZONS} horizons")
    if any(not 1 <= days <= MAX_STRESS_HORIZON_DAYS for days in horizons.values()):
        raise HTTPException(status_code=400, detail=f"horizons must be 1 to {MAX_STRESS_HORIZON_DAYS} days")
    return horizons


def _resolve_owner(request: Request, owner: str, identity: Optional[str]) -> Tuple[str, Path]:
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir is None:
        raise_owner_not_found(owner)
    assert owner_dir is not None  # raise_owner_not_found always raises; narrows the type for mypy
    ensure_owner_access(identity, owner_dir.name, accounts_root)
    return owner_dir.name, accounts_root


def _http_error(exc: Exception) -> HTTPException:
    """Map a strategy-store error to its HTTP status."""
    if isinstance(exc, BuiltinStrategyError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, StrategyNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, SettingsUnreadableError):
        return HTTPException(status_code=409, detail=UNREADABLE_DETAIL)
    return HTTPException(status_code=400, detail=str(exc))


_STORE_ERRORS = (BuiltinStrategyError, StrategyNotFoundError, SettingsUnreadableError, ValueError)


@router.get("/strategies/{owner}")
def get_strategies(owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    return {
        "strategies": [s.to_dict() for s in list_strategies(owner, accounts_root)],
        "active": active_strategy(owner, accounts_root),
    }


@router.post("/strategies/{owner}/stress")
def post_stress(owner: str, body: StressBody, request: Request, identity: Optional[str] = Depends(get_active_user)):
    """Replay a historical event against every strategy and the owner's portfolio (#9824).

    Body: ``event_id`` (catalogue id) or ``date`` (ISO), and ``horizons``
    (default 1m, 3m, 1y). See :func:`backend.common.strategy_stress.stress_strategies`.
    """
    owner, accounts_root = _resolve_owner(request, owner, identity)
    horizons = _stress_horizons(body.horizons)
    event = resolve_event(body.event_id, body.date)
    return stress_strategies(owner, event, horizons, accounts_root)


@router.get("/strategies/{owner}/{strategy_id}")
def get_one_strategy(
    owner: str, strategy_id: str, request: Request, identity: Optional[str] = Depends(get_active_user)
):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        return get_strategy(owner, strategy_id, accounts_root).to_dict()
    except StrategyNotFoundError as exc:
        raise _http_error(exc) from exc


@router.post("/strategies/{owner}", status_code=201)
def post_strategy(owner: str, body: StrategyBody, request: Request, identity: Optional[str] = Depends(get_active_user)):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        return create_strategy(owner, body.model_dump(), accounts_root).to_dict()
    except _STORE_ERRORS as exc:
        raise _http_error(exc) from exc


@router.put("/strategies/{owner}/{strategy_id}")
def put_strategy(
    owner: str,
    strategy_id: str,
    body: StrategyBody,
    request: Request,
    identity: Optional[str] = Depends(get_active_user),
):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        return update_strategy(owner, strategy_id, body.model_dump(exclude_none=True), accounts_root).to_dict()
    except _STORE_ERRORS as exc:
        raise _http_error(exc) from exc


@router.delete("/strategies/{owner}/{strategy_id}")
def remove_strategy(owner: str, strategy_id: str, request: Request, identity: Optional[str] = Depends(get_active_user)):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        delete_strategy(owner, strategy_id, accounts_root)
    except _STORE_ERRORS as exc:
        raise _http_error(exc) from exc
    return {"status": "deleted", "id": strategy_id}


@router.post("/strategies/{owner}/{strategy_id}/duplicate", status_code=201)
def post_duplicate(
    owner: str,
    strategy_id: str,
    request: Request,
    body: Optional[DuplicateBody] = None,
    identity: Optional[str] = Depends(get_active_user),
):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    name = body.name if body else None
    try:
        return duplicate_strategy(owner, strategy_id, name, accounts_root).to_dict()
    except _STORE_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post("/strategies/{owner}/{strategy_id}/apply")
def post_apply(
    owner: str, strategy_id: str, request: Request, identity: Optional[str] = Depends(get_active_user)
) -> Dict[str, Any]:
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        policy = apply_strategy(owner, strategy_id, accounts_root)
    except _STORE_ERRORS as exc:
        raise _http_error(exc) from exc
    return {"policy": policy.to_dict(), "active": active_strategy(owner, accounts_root)}
