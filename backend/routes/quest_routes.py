from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth import get_active_user
from backend import quests

router = APIRouter(prefix="/quests", tags=["quests"])


async def require_active_user(current_user: str | None = Depends(get_active_user)) -> str:
    """Resolve the authenticated user or raise ``401`` when missing."""

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return current_user


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
