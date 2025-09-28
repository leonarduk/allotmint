from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.auth import get_active_user, oauth2_scheme
from backend import quests

router = APIRouter(prefix="/quests", tags=["quests"])


async def require_active_user(
    request: Request, token: str | None = Depends(oauth2_scheme)
) -> str:
    """Resolve the authenticated user or raise ``401`` when missing."""

    user = await get_active_user(request, token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return user


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
