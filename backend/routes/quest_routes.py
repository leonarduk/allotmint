from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.auth import (
    get_active_user,
    get_current_user,
    resolve_current_user_override,
)
from backend.config import config, demo_identity
from backend import quests

router = APIRouter(prefix="/quests", tags=["quests"])


async def require_active_user(
    request: Request, current_user: str | None = Depends(get_active_user)
) -> str:
    """Resolve the authenticated user or raise ``401`` when missing."""

    if current_user:
        return current_user

    has_override, resolved = await resolve_current_user_override(request)
    if has_override and resolved:
        return resolved

    if config.disable_auth:
        return demo_identity()

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
