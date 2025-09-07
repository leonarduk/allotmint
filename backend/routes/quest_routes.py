from fastapi import APIRouter, Depends, HTTPException

from backend.auth import get_current_user
from backend import quests

router = APIRouter(prefix="/quests", tags=["quests"])


@router.get("/today")
async def today(current_user: str = Depends(get_current_user)):
    """Return today's quests for the authenticated user."""
    return quests.get_quests(current_user)


@router.post("/{quest_id}/complete")
async def complete(quest_id: str, current_user: str = Depends(get_current_user)):
    """Mark ``quest_id`` complete for the authenticated user."""
    try:
        return quests.mark_complete(current_user, quest_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Quest not found")
