from typing import Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend import alerts as alert_utils
from backend.common import data_loader
from backend.common.alerts import get_recent_alerts
from backend.common.errors import OWNER_NOT_FOUND
from backend.routes._accounts import resolve_accounts_root

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _validate_owner(user: str, request: Request) -> None:
    """Ensure ``user`` resolves to a known owner.

    The accounts root may occasionally point at an ephemeral dataset that
    doesn't include every demo owner.  Mirror the behaviour of
    :func:`backend.routes.portfolio.get_account` by falling back to the default
    repository data when the requested owner is missing. This keeps the route
    idempotent for smoke tests and development setups while still returning a
    404 when the owner is unknown everywhere.
    """

    accounts_root = resolve_accounts_root(request)
    owners = {o["owner"] for o in data_loader.list_plots(accounts_root)}
    if user in owners:
        return

    fallback_root = data_loader.resolve_paths(None, None).accounts_root
    if fallback_root != accounts_root:
        fallback_owners = {o["owner"] for o in data_loader.list_plots(fallback_root)}
        if user in fallback_owners:
            request.app.state.accounts_root = fallback_root
            return

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
    alert_utils.set_user_push_subscription(user, payload.model_dump())
    return {"status": "ok"}


@router.delete("/push-subscription/{user}")
async def delete_push_subscription(user: str, request: Request):
    """Remove the Web Push subscription for ``user`` if present."""
    try:
        _validate_owner(user, request)
    except HTTPException as exc:
        # Treat missing owners as an already-deleted subscription. Smoke tests
        # run against ephemeral datasets that may not include every owner and
        # the route should remain idempotent regardless.
        if exc.status_code != 404:
            raise
        return {"status": "deleted"}
    alert_utils.remove_user_push_subscription(user)
    return {"status": "deleted"}
