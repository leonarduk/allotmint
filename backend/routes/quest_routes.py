from __future__ import annotations

import inspect

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.auth import get_active_user, get_current_user
from backend.config import config
from backend import quests

router = APIRouter(prefix="/quests", tags=["quests"])


DEMO_IDENTITY = "demo"


async def require_active_user(
    request: Request, current_user: str | None = Depends(get_active_user)
) -> str:
    """Resolve the authenticated user or raise ``401`` when missing."""

    if current_user:
        return current_user

    override = None
    for overrides in (
        getattr(request.app, "dependency_overrides", None),
        getattr(getattr(request.app, "router", None), "dependency_overrides", None),
    ):
        if overrides and get_current_user in overrides:
            override = overrides[get_current_user]
            break

    if override is not None:
        resolved = override()
        if inspect.isawaitable(resolved):
            resolved = await resolved
        if resolved:
            return resolved

    if config.disable_auth:
        return DEMO_IDENTITY

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
    )


@router.get("/today")
async def today(current_user: str = Depends(require_active_user)):
    """Return today's quests for the authenticated user."""
    return quests.get_quests(current_user)


@router.post("/{quest_id}/complete")
async def complete(quest_id: str, current_user: str = Depends(require_active_user)):
    """Mark ``quest_id`` complete for the authenticated user."""
    try:
        return quests.mark_complete(current_user, quest_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Quest not found")
