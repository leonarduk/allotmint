"""Contribution and allowance guardian routes (#10479).

- ``GET /allowance-guardian/{owner}``: the guardian report (computed on request).
- ``GET /allowance-guardian/{owner}/schedule``: the owner's expected contributions.
- ``PUT /allowance-guardian/{owner}/schedule``: replace them (the owner's edit; the
  guardian itself never writes).

Access follows ``/plans/{owner}`` (:mod:`backend.routes.investment_plan`): the owner
must exist under the accounts root and pass :func:`ensure_owner_access`; schedules
are stored beside that accounts root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import ValidationError

from backend.allowance_guardian import run
from backend.allowance_guardian.schedule import load_schedule, parse_schedule, save_schedule
from backend.auth import get_active_user
from backend.common.authz import ensure_owner_access
from backend.common.errors import raise_owner_not_found
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory

router = APIRouter(prefix="/allowance-guardian", tags=["allowance-guardian"])


def _validation_detail(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        msg = str(err.get("msg", "")).removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)


def _resolve_owner(request: Request, owner: str, identity: Optional[str]) -> Tuple[str, Path]:
    """Canonical owner id and data root (the accounts root's parent), after the access check."""
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir is None:
        raise_owner_not_found(owner)
    assert owner_dir is not None  # raise_owner_not_found always raises; narrows the type for mypy
    ensure_owner_access(identity, owner_dir.name, accounts_root)
    return owner_dir.name, Path(accounts_root).parent


def _load(owner: str, data_root: Path):
    try:
        return load_schedule(owner, data_root)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=f"Saved schedule for {owner} is invalid: {_validation_detail(exc)}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Saved schedule for {owner} is invalid: {exc}") from exc


@router.get("/{owner}")
def guardian_report(owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)) -> Dict[str, Any]:
    owner, data_root = _resolve_owner(request, owner, identity)
    schedule = _load(owner, data_root)
    return run(owner, data_root=data_root, schedule=schedule.contributions)


@router.get("/{owner}/schedule")
def get_schedule(owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)) -> Dict[str, Any]:
    owner, data_root = _resolve_owner(request, owner, identity)
    return _load(owner, data_root).model_dump(mode="json")


@router.put("/{owner}/schedule")
def put_schedule(
    owner: str,
    request: Request,
    body: Dict[str, Any] = Body(...),
    identity: Optional[str] = Depends(get_active_user),
) -> Dict[str, Any]:
    owner, data_root = _resolve_owner(request, owner, identity)
    data = {**body, "owner": owner if body.get("owner") is None else body["owner"]}
    try:
        schedule = parse_schedule(data, owner)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=_validation_detail(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_schedule(schedule, data_root)
    return schedule.model_dump(mode="json")
