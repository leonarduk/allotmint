from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend import alerts as alert_utils
from backend.auth import get_current_user

router = APIRouter(prefix="/alert-thresholds", tags=["alerts"])


class ThresholdPayload(BaseModel):
    threshold: float


@router.get("/{user}")
async def get_threshold(user: str, current_user: str = Depends(get_current_user)):
    """Return the alert threshold configured for ``user``."""
    if user != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Owner mismatch"
        )
    return {"threshold": alert_utils.get_user_threshold(user)}


@router.post("/{user}")
async def set_threshold(
    user: str,
    payload: ThresholdPayload,
    current_user: str = Depends(get_current_user),
):
    """Update the alert threshold for ``user``."""
    if user != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Owner mismatch"
        )
    alert_utils.set_user_threshold(user, payload.threshold)
    return {"threshold": payload.threshold}
