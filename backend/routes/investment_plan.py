# backend/routes/investment_plan.py
"""Owner-scoped read/write of the investment plan record (#9547).

Access follows the other ``/{owner}`` routes (e.g. ``/rebalance/{owner}``):
the owner must exist under the accounts root and the caller must pass
:func:`backend.common.authz.ensure_owner_access`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import ValidationError

from backend.auth import get_active_user
from backend.common.allocation_policy import load_allocation_policy
from backend.common.investment_plan import (
    InvestmentPlan,
    PlanNotFoundError,
    compare_with_rebalance_targets,
    load_plan,
    parse_plan,
    save_plan,
    vehicle_warnings,
)
from backend.routes.rebalance import _resolve_owner

router = APIRouter(tags=["investment-plan"])


def _validation_detail(exc: ValidationError) -> str:
    """One readable line per error, e.g. ``target: Target weights must sum to 100%``."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        msg = str(err.get("msg", "")).removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)


def _response(plan: InvestmentPlan, owner: str, accounts_root: Any) -> Dict[str, Any]:
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
        plan = load_plan(owner)
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
    data = {**body, "owner": body.get("owner", owner)}
    try:
        plan = parse_plan(data, owner)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=_validation_detail(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_plan(plan)
    return _response(plan, owner, accounts_root)
