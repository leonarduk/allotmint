from pathlib import Path
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from backend import alerts as alert_utils
from backend.auth import get_owner_check_identity
from backend.common import data_loader
from backend.common.alerts import get_recent_alerts
from backend.common.authz import ensure_owner_access
from backend.common.errors import OwnerNotFoundError, raise_owner_not_found
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


@router.get("/")
def alerts():
    """Return recent alert messages."""
    return get_recent_alerts()


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
