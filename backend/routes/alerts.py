from typing import Dict

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


class PushSubscriptionPayload(BaseModel):
    endpoint: str
    keys: Dict[str, str]


@router.get("/settings/{user}")
async def get_settings(user: str):
    """Return the alert threshold configured for ``user``."""
    return {"threshold": alert_utils.get_user_threshold(user)}


@router.post("/settings/{user}")
async def set_settings(user: str, payload: ThresholdPayload):
    """Update the alert threshold for ``user``."""
    alert_utils.set_user_threshold(user, payload.threshold)
    return {"threshold": payload.threshold}


@router.post("/push-subscription/{user}")
async def add_push_subscription(user: str, payload: PushSubscriptionPayload):
    """Persist a Web Push subscription for ``user``."""
    alert_utils.set_user_push_subscription(user, payload.dict())
    return {"status": "ok"}


@router.delete("/push-subscription/{user}")
async def delete_push_subscription(user: str):
    """Remove the Web Push subscription for ``user`` if present."""
    alert_utils.remove_user_push_subscription(user)
    return {"status": "deleted"}
