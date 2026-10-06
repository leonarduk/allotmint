# backend/routes/investment_plan.py
"""Owner-scoped read/write of the investment plan record (#9547).

Access follows the other ``/{owner}`` routes (e.g. ``/rebalance/{owner}``):
the owner must exist under the accounts root and the caller must pass
:func:`backend.common.authz.ensure_owner_access`. Plans are stored beside that
same accounts root (``<accounts_root>/../plans``), so the root the route
validated against is the root it reads and writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import ValidationError

from backend.auth import get_active_user
from backend.common.allocation_policy import load_allocation_policy
from backend.common.authz import ensure_owner_access
from backend.common.errors import raise_owner_not_found
from backend.common.investment_plan import (
    InvestmentPlan,
    PlanNotFoundError,
    compare_with_rebalance_targets,
    load_plan,
    parse_plan,
    save_plan,
    vehicle_warnings,
)
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory

router = APIRouter(tags=["investment-plan"])


def _validation_detail(exc: ValidationError) -> str:
    """One readable line per error, e.g. ``target: Target weights must sum to 100%``."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        msg = str(err.get("msg", "")).removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)


def _resolve_owner(request: Request, owner: str, identity: Optional[str]) -> Tuple[str, Path]:
    """Canonical owner id and accounts root, after the owner-access check."""
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir is None:
        raise_owner_not_found(owner)
    ensure_owner_access(identity, owner_dir.name, accounts_root)
    return owner_dir.name, accounts_root


def _data_root(accounts_root: Path) -> Path:
    return Path(accounts_root).parent


def _response(plan: InvestmentPlan, owner: str, accounts_root: Path) -> Dict[str, Any]:
    policy = load_allocation_policy(owner, accounts_root)
    return {
        "plan": plan.to_dict(),
        "warnings": vehicle_warnings(plan),
        "rebalance": compare_with_rebalance_targets(plan, policy),
    }


@router.get("/plans/{owner}")
def get_investment_plan(owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        plan = load_plan(owner, _data_root(accounts_root))
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=f"Saved plan for {owner} is invalid: {_validation_detail(exc)}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Saved plan for {owner} is invalid: {exc}") from exc
    return _response(plan, owner, accounts_root)


@router.put("/plans/{owner}")
def put_investment_plan(
    owner: str,
    request: Request,
    body: Dict[str, Any] = Body(...),
    identity: Optional[str] = Depends(get_active_user),
):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    # Only a missing/null owner defaults to the path owner; any other value is validated.
    data = {**body, "owner": owner if body.get("owner") is None else body["owner"]}
    try:
        plan = parse_plan(data, owner)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=_validation_detail(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Build the response first so a failure there cannot follow a completed write.
    response = _response(plan, owner, accounts_root)
    save_plan(plan, _data_root(accounts_root))
    return response
