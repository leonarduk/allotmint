from typing import Dict

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from backend import alerts as alert_utils
from backend.common import data_loader
from backend.common.alerts import get_recent_alerts
from backend.common.errors import OWNER_NOT_FOUND

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _validate_owner(user: str, request: Request) -> None:
    owners = {o["owner"] for o in data_loader.list_plots(request.app.state.accounts_root)}
    if user not in owners:
        raise HTTPException(status_code=404, detail=OWNER_NOT_FOUND)


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
async def get_settings(user: str, request: Request):
    """Return the alert threshold configured for ``user``."""
    _validate_owner(user, request)
    return {"threshold": alert_utils.get_user_threshold(user)}


@router.post("/settings/{user}")
async def set_settings(user: str, payload: ThresholdPayload, request: Request):
    """Update the alert threshold for ``user``."""
    _validate_owner(user, request)
    alert_utils.set_user_threshold(user, payload.threshold)
    return {"threshold": payload.threshold}


@router.post("/push-subscription/{user}")
async def add_push_subscription(user: str, payload: PushSubscriptionPayload, request: Request):
    """Persist a Web Push subscription for ``user``."""
    _validate_owner(user, request)
    alert_utils.set_user_push_subscription(user, payload.dict())
    return {"status": "ok"}


@router.delete("/push-subscription/{user}")
async def delete_push_subscription(user: str, request: Request):
    """Remove the Web Push subscription for ``user`` if present."""
    _validate_owner(user, request)
    alert_utils.remove_user_push_subscription(user)
    return {"status": "deleted"}
