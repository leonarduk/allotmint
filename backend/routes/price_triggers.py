"""CRUD routes for user price triggers (see :mod:`backend.price_triggers`)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, NoReturn, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend import price_triggers as triggers
from backend.auth import get_active_user
from backend.routes.alert_settings import _resolve_identity, _validate_owner

router = APIRouter(prefix="/price-triggers", tags=["alerts"])


class TriggerCreate(BaseModel):
    ticker: str
    condition: Literal["above", "below"]
    price: float = Field(gt=0)
    mode: Literal["once", "continuous"] = "once"
    note: Optional[str] = None
    enabled: bool = True


class TriggerUpdate(BaseModel):
    ticker: Optional[str] = None
    condition: Optional[Literal["above", "below"]] = None
    price: Optional[float] = Field(default=None, gt=0)
    mode: Optional[Literal["once", "continuous"]] = None
    note: Optional[str] = None
    enabled: Optional[bool] = None


async def _identity(user: str, request: Request, current_user: str | None) -> str:
    identity = await _resolve_identity(request, current_user)
    _validate_owner(user, identity)
    return identity


def _raise(exc: triggers.TriggerError) -> NoReturn:
    missing = isinstance(exc, triggers.TriggerNotFound)
    code = status.HTTP_404_NOT_FOUND if missing else status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("/{user}")
async def list_triggers(
    user: str,
    request: Request,
    current_user: str | None = Depends(get_active_user),
) -> List[Dict[str, Any]]:
    """Return the price triggers configured for ``user``."""
    return triggers.list_triggers(await _identity(user, request, current_user))


@router.post("/{user}", status_code=status.HTTP_201_CREATED)
async def create_trigger(
    user: str,
    payload: TriggerCreate,
    request: Request,
    current_user: str | None = Depends(get_active_user),
) -> Dict[str, Any]:
    identity = await _identity(user, request, current_user)
    try:
        return triggers.create_trigger(identity, **payload.model_dump())
    except triggers.TriggerError as exc:
        _raise(exc)


@router.patch("/{user}/{trigger_id}")
async def update_trigger(
    user: str,
    trigger_id: str,
    payload: TriggerUpdate,
    request: Request,
    current_user: str | None = Depends(get_active_user),
) -> Dict[str, Any]:
    identity = await _identity(user, request, current_user)
    try:
        return triggers.update_trigger(identity, trigger_id, **payload.model_dump(exclude_unset=True))
    except triggers.TriggerError as exc:
        _raise(exc)


@router.delete("/{user}/{trigger_id}")
async def delete_trigger(
    user: str,
    trigger_id: str,
    request: Request,
    current_user: str | None = Depends(get_active_user),
) -> Dict[str, Any]:
    identity = await _identity(user, request, current_user)
    try:
        return {"status": "deleted", "trigger": triggers.delete_trigger(identity, trigger_id)}
    except triggers.TriggerError as exc:
        _raise(exc)
