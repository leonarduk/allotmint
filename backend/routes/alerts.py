from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend import alerts as alert_utils
from backend.auth import (
    get_owner_check_identity,
    is_demo_request,
    owner_access_enforced_under_disable_auth,
    request_identity,
)
from backend.common import data_loader
from backend.common.alerts import get_recent_alerts
from backend.common.authz import ensure_owner_access
from backend.common.errors import OwnerNotFoundError, raise_owner_not_found
from backend.config import config
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _validate_owner(user: str, request: Request) -> Tuple[str, Path]:
    """Ensure ``user`` resolves to a known owner; return its canonical name and accounts root.

    The accounts root may occasionally point at an ephemeral dataset that
    doesn't include every demo owner.  Mirror the behaviour of
    :func:`backend.routes.portfolio.get_account` by falling back to the default
    repository data when the requested owner is missing. This keeps the route
    idempotent for smoke tests and development setups while still returning a
    404 when the owner is unknown everywhere.
    """

    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, user)
    if owner_dir:
        return _canonical(owner_dir, user), Path(accounts_root)

    fallback_root = data_loader.resolve_paths(None, None).accounts_root
    # ``resolve_accounts_root`` returns a resolved ``Path`` instance, but avoid
    # assuming callers do the same when the fallback root is injected via
    # configuration.
    if Path(fallback_root) != Path(accounts_root):
        owner_dir = resolve_owner_directory(fallback_root, user)
        if owner_dir:
            request.app.state.accounts_root = Path(fallback_root).expanduser().resolve(strict=False)
            return _canonical(owner_dir, user), Path(fallback_root)

    raise_owner_not_found(user)
    raise AssertionError("unreachable")  # raise_owner_not_found always raises


def _canonical(owner_dir: object, user: str) -> str:
    """The on-disk owner directory name, or ``user`` when no path was returned."""
    return owner_dir.name if isinstance(owner_dir, Path) else user


def _authorised_owner(user: str, request: Request, identity: Optional[str]) -> None:
    """Resolve ``user`` as :func:`_validate_owner` does, then check the caller may act on it (#11351).

    The check runs against the accounts root the owner was found under, on the
    canonical directory name, so it reads the right ``person.json``.
    """
    owner, accounts_root = _validate_owner(user, request)
    ensure_owner_access(identity, owner, accounts_root)


def _owner_filter_applies() -> bool:
    """Whether ``GET /alerts/`` must hide other owners' alerts.

    Not with ``disable_auth`` and ``ENFORCE_OWNER_ACCESS`` off, where every
    owner is visible, unless the request carries a demo token.
    """
    return is_demo_request() or not config.disable_auth or owner_access_enforced_under_disable_auth()


def _visible_owners(identity: Optional[str]) -> Set[str]:
    """Lower-cased owner ids the caller may see, by the ``/owners`` rule.

    ``list_plots(current_user=identity)`` gives the signed-in user's owners
    with auth enabled, the request identity's under ``ENFORCE_OWNER_ACCESS``,
    and only the demo owner for a demo token. The caller's own identity is
    added too, for alerts keyed by it (a nudge subscribed by email).
    """
    try:
        plots = data_loader.list_plots(current_user=identity)
    except data_loader.ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail="Account data provider unavailable") from exc
    visible = {p.owner.strip().lower() for p in plots}
    caller = identity if identity is not None else request_identity()
    if isinstance(caller, str) and caller.strip() and not is_demo_request():
        visible.add(caller.strip().lower())
    return visible


def _visible_alerts(alerts: List[Dict], identity: Optional[str]) -> List[Dict]:
    """``alerts`` without those about owners the caller may not see (#11359).

    An alert with no ``owner`` is global (price triggers, agent signals) and
    always shown. That includes alerts stored before owners were recorded;
    they age out under ``MAX_STORED_ALERTS``.
    """
    if not _owner_filter_applies():
        return alerts
    visible = _visible_owners(identity)
    shown = []
    for alert in alerts:
        owner = alert.get("owner") if isinstance(alert, dict) else None
        if not isinstance(owner, str) or not owner.strip() or owner.strip().lower() in visible:
            shown.append(alert)
    return shown


@router.get("/")
def alerts(identity: Optional[str] = Depends(get_owner_check_identity)):
    """Return recent alert messages the caller may see."""
    return _visible_alerts(get_recent_alerts(), identity)


class ThresholdPayload(BaseModel):
    threshold: float


class PushSubscriptionPayload(BaseModel):
    endpoint: str
    keys: Dict[str, str]


@router.get("/settings/{user}")
def get_settings(user: str, request: Request, identity: Optional[str] = Depends(get_owner_check_identity)):
    """Return the alert threshold configured for ``user``."""
    _authorised_owner(user, request, identity)
    return {"threshold": alert_utils.get_user_threshold(user)}


@router.post("/settings/{user}")
def set_settings(
    user: str, payload: ThresholdPayload, request: Request, identity: Optional[str] = Depends(get_owner_check_identity)
):
    """Update the alert threshold for ``user``."""
    _authorised_owner(user, request, identity)
    alert_utils.set_user_threshold(user, payload.threshold)
    return {"threshold": payload.threshold}


@router.post("/push-subscription/{user}")
def add_push_subscription(
    user: str,
    payload: PushSubscriptionPayload,
    request: Request,
    identity: Optional[str] = Depends(get_owner_check_identity),
):
    """Persist a Web Push subscription for ``user``."""
    _authorised_owner(user, request, identity)
    alert_utils.set_user_push_subscription(user, payload.model_dump())
    return {"status": "ok"}


@router.delete("/push-subscription/{user}")
def delete_push_subscription(user: str, request: Request, identity: Optional[str] = Depends(get_owner_check_identity)):
    """Remove the Web Push subscription for ``user`` if present."""
    try:
        _authorised_owner(user, request, identity)
    except OwnerNotFoundError:
        # Treat missing owners as an already-deleted subscription. Smoke tests
        # run against ephemeral datasets that may not include every owner and
        # the route should remain idempotent regardless.
        return {"status": "deleted"}
    alert_utils.remove_user_push_subscription(user)
    return {"status": "deleted"}
