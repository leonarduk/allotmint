# backend/routes/cash_deployment.py
"""Cash deployment tracker API (#10480).

The owner's own schedules are the only thing written here. ``GET
/cash-deployment/{owner}`` returns the read-only bot run (:func:`run`): each
schedule's progress and, when a tranche is due, its draft order list per the
owner's plan.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.auth import get_active_user
from backend.cash_deployment import schedule as schedule_store
from backend.cash_deployment.bot import OwnerContext, evaluate_schedule, run
from backend.cash_deployment.schedule import ScheduleInput, ScheduleNotFoundError
from backend.common.authz import ensure_owner_access
from backend.common.errors import raise_owner_not_found
from backend.common.settings_file import SettingsUnreadableError
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory

router = APIRouter(tags=["cash-deployment"])

_UNREADABLE = "Owner settings file is unreadable; fix or remove it before saving a schedule"
_UNREADABLE_READ = "Owner settings file is unreadable; fix or remove it to see cash deployment schedules"
_NOT_FOUND = "No cash deployment schedule with that id"


def _resolve_owner(request: Request, owner: str, identity: Optional[str]) -> Tuple[str, Path]:
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir is None:
        raise_owner_not_found(owner)
    assert owner_dir is not None  # raise_owner_not_found always raises; narrows the type for mypy
    ensure_owner_access(identity, owner_dir.name, accounts_root)
    return owner_dir.name, accounts_root


def _check_account(owner: str, accounts_root: Path, account: str) -> None:
    if not (accounts_root / owner / f"{account}.json").is_file():
        raise HTTPException(status_code=400, detail=f"Unknown account {account!r}")


@router.get("/cash-deployment/{owner}")
def get_cash_deployment(
    owner: str, request: Request, as_of: Optional[date] = None, identity: Optional[str] = Depends(get_active_user)
) -> Dict[str, Any]:
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        return run(owner, as_of, accounts_root=accounts_root)
    except SettingsUnreadableError as exc:
        raise HTTPException(status_code=409, detail=_UNREADABLE_READ) from exc


@router.get("/cash-deployment/{owner}/schedules/{schedule_id}")
def get_schedule(
    owner: str,
    schedule_id: str,
    request: Request,
    as_of: Optional[date] = None,
    identity: Optional[str] = Depends(get_active_user),
) -> Dict[str, Any]:
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        schedule = schedule_store.get_schedule(owner, schedule_id, accounts_root)
    except ScheduleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    return evaluate_schedule(schedule, OwnerContext(owner, accounts_root), as_of or date.today())


@router.post("/cash-deployment/{owner}/schedules", status_code=201)
def create_schedule(
    owner: str, body: ScheduleInput, request: Request, identity: Optional[str] = Depends(get_active_user)
) -> Dict[str, Any]:
    owner, accounts_root = _resolve_owner(request, owner, identity)
    _check_account(owner, accounts_root, body.account)
    try:
        return schedule_store.create_schedule(owner, body, accounts_root).to_dict()
    except SettingsUnreadableError as exc:
        raise HTTPException(status_code=409, detail=_UNREADABLE) from exc


@router.put("/cash-deployment/{owner}/schedules/{schedule_id}")
def update_schedule(
    owner: str,
    schedule_id: str,
    body: ScheduleInput,
    request: Request,
    identity: Optional[str] = Depends(get_active_user),
) -> Dict[str, Any]:
    owner, accounts_root = _resolve_owner(request, owner, identity)
    _check_account(owner, accounts_root, body.account)
    try:
        return schedule_store.update_schedule(owner, schedule_id, body, accounts_root).to_dict()
    except ScheduleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except SettingsUnreadableError as exc:
        raise HTTPException(status_code=409, detail=_UNREADABLE) from exc


@router.delete("/cash-deployment/{owner}/schedules/{schedule_id}")
def delete_schedule(
    owner: str, schedule_id: str, request: Request, identity: Optional[str] = Depends(get_active_user)
) -> Dict[str, str]:
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        schedule_store.delete_schedule(owner, schedule_id, accounts_root)
    except ScheduleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except SettingsUnreadableError as exc:
        raise HTTPException(status_code=409, detail=_UNREADABLE) from exc
    return {"deleted": schedule_id}
