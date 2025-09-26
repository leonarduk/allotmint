from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend import alerts as alert_utils
from backend.auth import get_active_user

DEMO_IDENTITY = "demo"

router = APIRouter(prefix="/alert-thresholds", tags=["alerts"])


class ThresholdPayload(BaseModel):
    threshold: float


def _validate_owner(user: str, current_user: str) -> None:
    """Ensure requests only act on the authenticated user's settings."""
    if user != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Owner mismatch"
        )


@router.get("/{user}")
async def get_threshold(user: str, current_user: str | None = Depends(get_active_user)):
    """Return the alert threshold configured for ``user``."""
    identity = current_user or DEMO_IDENTITY
    _validate_owner(user, identity)
    return {"threshold": alert_utils.get_user_threshold(identity)}


@router.post("/{user}")
async def set_threshold(
    user: str,
    payload: ThresholdPayload,
    current_user: str | None = Depends(get_active_user),
):
    """Update the alert threshold for ``user``."""
    identity = current_user or DEMO_IDENTITY
    _validate_owner(user, identity)
    alert_utils.set_user_threshold(identity, payload.threshold)
    return {"threshold": payload.threshold}

