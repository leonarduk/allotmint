from fastapi import APIRouter
from pydantic import BaseModel

from backend import alerts as alert_utils
from backend.common.alerts import get_recent_alerts

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/")
async def alerts():
    """Return recent alert messages."""
    return get_recent_alerts()


class ThresholdPayload(BaseModel):
    threshold: float


@router.get("/settings/{user}")
async def get_settings(user: str):
    """Return the alert threshold configured for ``user``."""
    return {"threshold": alert_utils.get_user_threshold(user)}


@router.post("/settings/{user}")
async def set_settings(user: str, payload: ThresholdPayload):
    """Update the alert threshold for ``user``."""
    alert_utils.set_user_threshold(user, payload.threshold)
    return {"threshold": payload.threshold}
