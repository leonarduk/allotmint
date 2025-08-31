from fastapi import APIRouter
from pydantic import BaseModel

from backend import alerts as alert_utils

router = APIRouter(prefix="/alert-thresholds", tags=["alerts"])


class ThresholdPayload(BaseModel):
    threshold: float


@router.get("/{user}")
async def get_threshold(user: str):
    """Return the alert threshold configured for ``user``."""
    return {"threshold": alert_utils.get_user_threshold(user)}


@router.post("/{user}")
async def set_threshold(user: str, payload: ThresholdPayload):
    """Update the alert threshold for ``user``."""
    alert_utils.set_user_threshold(user, payload.threshold)
    return {"threshold": payload.threshold}
