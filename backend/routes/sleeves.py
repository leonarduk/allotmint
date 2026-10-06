# backend/routes/sleeves.py
"""Owner-scoped sleeves for running more than one strategy at once (#9813).

``/sleeves/{owner}`` lists the core sleeve (sized by the rest, targeted by the
allocation policy) and the owner's other sleeves, the ticker tags, and the
owner's holdings so the page can tag them. Access follows ``/strategies``.
It is a separate prefix because ``/strategies/{owner}/{strategy_id}`` would
otherwise swallow ``/strategies/{owner}/sleeves``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.auth import get_active_user
from backend.common import portfolio as portfolio_mod
from backend.common.allocation_policy import load_allocation_policy
from backend.common.authz import ensure_owner_access
from backend.common.errors import raise_owner_not_found
from backend.common.settings_file import SettingsUnreadableError
from backend.common.sleeves import (
    CORE_ID,
    CORE_NAME,
    CoreSleeveError,
    SleeveNotFoundError,
    SleeveSetup,
    apply_strategy_to_sleeve,
    assign_ticker,
    create_sleeve,
    delete_sleeve,
    load_sleeves,
    update_sleeve,
)
from backend.common.strategies import StrategyNotFoundError, active_strategy
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory

router = APIRouter(tags=["sleeves"])

UNREADABLE_DETAIL = "Owner settings file is unreadable; fix or remove it before saving sleeves"


class SleeveBody(BaseModel):
    name: Optional[str] = None
    size_pct: Optional[float] = None
    targets: Optional[Dict[str, float]] = None
    strategy_id: Optional[str] = None


class AssignmentBody(BaseModel):
    sleeve_id: Optional[str] = None


def _resolve_owner(request: Request, owner: str, identity: Optional[str]) -> Tuple[str, Path]:
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir is None:
        raise_owner_not_found(owner)
    assert owner_dir is not None  # raise_owner_not_found always raises; narrows the type for mypy
    ensure_owner_access(identity, owner_dir.name, accounts_root)
    return owner_dir.name, accounts_root


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (SleeveNotFoundError, StrategyNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, CoreSleeveError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, SettingsUnreadableError):
        return HTTPException(status_code=409, detail=UNREADABLE_DETAIL)
    return HTTPException(status_code=400, detail=str(exc))


_STORE_ERRORS = (SleeveNotFoundError, StrategyNotFoundError, SettingsUnreadableError, ValueError)


def _holdings(owner: str, accounts_root: Path, setup: SleeveSetup) -> list[dict[str, Any]]:
    """Every held ticker with its total GBP value and current sleeve, largest first."""
    try:
        portfolio = portfolio_mod.build_owner_portfolio(owner, accounts_root)
    except FileNotFoundError:
        raise_owner_not_found(owner)
    rows: dict[str, dict[str, Any]] = {}
    for account in portfolio.get("accounts") or []:
        for holding in account.get("holdings") or []:
            ticker = str(holding.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            row = rows.setdefault(
                ticker,
                {"ticker": ticker, "name": holding.get("name"), "value": 0.0, "sleeve_id": setup.sleeve_of(ticker)},
            )
            try:
                row["value"] += float(holding.get("market_value_gbp") or 0.0)
            except (TypeError, ValueError):
                continue
    for row in rows.values():
        row["value"] = round(row["value"], 2)
    return sorted(rows.values(), key=lambda r: (-r["value"], r["ticker"]))


def _listing(owner: str, accounts_root: Path, include_holdings: bool = True) -> Dict[str, Any]:
    setup = load_sleeves(owner, accounts_root)
    core = {
        "id": CORE_ID,
        "name": CORE_NAME,
        "size_pct": setup.core_size_pct,
        "targets": load_allocation_policy(owner, accounts_root).targets,
        "strategy": active_strategy(owner, accounts_root),
    }
    body: Dict[str, Any] = {
        "sleeves": [core, *(s.to_dict() for s in setup.sleeves)],
        "assignments": dict(sorted(setup.assignments.items())),
    }
    if include_holdings:
        body["holdings"] = _holdings(owner, accounts_root, setup)
    return body


@router.get("/sleeves/{owner}")
def get_sleeves(owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    return _listing(owner, accounts_root)


@router.post("/sleeves/{owner}", status_code=201)
def post_sleeve(owner: str, body: SleeveBody, request: Request, identity: Optional[str] = Depends(get_active_user)):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        return create_sleeve(owner, body.model_dump(), accounts_root).to_dict()
    except _STORE_ERRORS as exc:
        raise _http_error(exc) from exc


@router.put("/sleeves/{owner}/assignments/{ticker}")
def put_assignment(
    owner: str,
    ticker: str,
    body: AssignmentBody,
    request: Request,
    identity: Optional[str] = Depends(get_active_user),
):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        assign_ticker(owner, ticker, body.sleeve_id, accounts_root)
    except _STORE_ERRORS as exc:
        raise _http_error(exc) from exc
    return _listing(owner, accounts_root, include_holdings=False)


@router.put("/sleeves/{owner}/{sleeve_id}")
def put_sleeve(
    owner: str,
    sleeve_id: str,
    body: SleeveBody,
    request: Request,
    identity: Optional[str] = Depends(get_active_user),
):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        return update_sleeve(owner, sleeve_id, body.model_dump(exclude_none=True), accounts_root).to_dict()
    except _STORE_ERRORS as exc:
        raise _http_error(exc) from exc


@router.delete("/sleeves/{owner}/{sleeve_id}")
def remove_sleeve(owner: str, sleeve_id: str, request: Request, identity: Optional[str] = Depends(get_active_user)):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        delete_sleeve(owner, sleeve_id, accounts_root)
    except _STORE_ERRORS as exc:
        raise _http_error(exc) from exc
    return {"status": "deleted", "id": sleeve_id}


@router.post("/sleeves/{owner}/{sleeve_id}/apply/{strategy_id}")
def post_apply(
    owner: str,
    sleeve_id: str,
    strategy_id: str,
    request: Request,
    identity: Optional[str] = Depends(get_active_user),
):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        return apply_strategy_to_sleeve(owner, sleeve_id, strategy_id, accounts_root).to_dict()
    except _STORE_ERRORS as exc:
        raise _http_error(exc) from exc
