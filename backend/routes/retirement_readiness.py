"""Retirement readiness monitor routes (#10484).

``GET  /retirement-readiness/{owner}/latest``  the latest stored report
``GET  /retirement-readiness/{owner}/history`` one trend point per stored run
``POST /retirement-readiness/{owner}/run``     run the monitor now and store it

Access follows the other ``/{owner}`` routes (e.g. ``/plans/{owner}``). The
run writes only the monitor's own report; the owner's plan and data are read.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.auth import get_active_user
from backend.common.authz import ensure_owner_access
from backend.common.errors import raise_owner_not_found
from backend.retirement import history
from backend.retirement.readiness import ReadinessError, run
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory

router = APIRouter(prefix="/retirement-readiness", tags=["retirement-readiness"])


def _owner(request: Request, owner: str, identity: Optional[str]) -> str:
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir is None:
        raise_owner_not_found(owner)
    assert owner_dir is not None  # raise_owner_not_found always raises; narrows the type for mypy
    ensure_owner_access(identity, owner_dir.name, accounts_root)
    return owner_dir.name


def _runs(owner: str) -> List[Dict[str, Any]]:
    try:
        return history.load_runs(owner)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{owner}/latest")
def latest(owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)):
    owner = _owner(request, owner, identity)
    runs = _runs(owner)
    if not runs:
        raise HTTPException(status_code=404, detail=f"No retirement readiness report stored for {owner}")
    return runs[-1]


@router.get("/{owner}/history")
def run_history(owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)):
    owner = _owner(request, owner, identity)
    return {"owner": owner, "trend": history.trend(_runs(owner))}


def _survival_levels(raw: Optional[str]) -> Tuple[Optional[List[float]], Optional[str]]:
    if raw is None:
        return None, None
    try:
        return [float(part) for part in raw.split(",") if part.strip()], None
    except ValueError:
        return None, "survival_levels must be comma-separated percentages, e.g. 90,95,100"


@router.post("/{owner}/run")
def run_now(
    owner: str,
    request: Request,
    identity: Optional[str] = Depends(get_active_user),
    survival_levels: Annotated[Optional[str], Query(description="Comma-separated, e.g. 90,95,100")] = None,
    floor_gbp: Annotated[Optional[float], Query(ge=0)] = None,
    death_age: Annotated[Optional[int], Query(ge=1, le=120)] = None,
    retirement_age: Annotated[Optional[int], Query(ge=0, le=100)] = None,
    state_pension_annual: Annotated[Optional[float], Query(ge=0)] = None,
    contribution_annual: Annotated[Optional[float], Query(ge=0)] = None,
    investment_growth_pct: Annotated[Optional[float], Query(ge=-50, le=50)] = None,
    assumed_inflation_pct: Annotated[Optional[float], Query(ge=-10, le=50)] = None,
):
    owner = _owner(request, owner, identity)
    levels, error = _survival_levels(survival_levels)
    if error:
        raise HTTPException(status_code=400, detail=error)
    overrides = {
        "survival_levels": levels,
        "floor_gbp": floor_gbp,
        "death_age": death_age,
        "retirement_age": retirement_age,
        "state_pension_annual": state_pension_annual,
        "contribution_annual": contribution_annual,
        "investment_growth_pct": investment_growth_pct,
        "assumed_inflation_pct": assumed_inflation_pct,
    }
    try:
        return run(owner, overrides=overrides, request=request)
    except ReadinessError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
