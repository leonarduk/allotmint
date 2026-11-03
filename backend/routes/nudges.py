"""Nudge subscription, snooze and feed routes.

A nudge's ``user`` is whatever the subscription was keyed by: usually an
owner id, sometimes the signed-in identity itself. Either way the caller must
be allowed to act for it (#11353): :func:`ensure_owner_access` allows the
owner id itself, the owner's ``email`` and its ``viewers``, and for a ``user``
with no ``person.json`` only the identity equal to it. ``GET /nudges/`` shows
the same set, so every id the notifications drawer offers to snooze or
re-schedule is one the caller may act on. With ``disable_auth`` and
``ENFORCE_OWNER_ACCESS`` off the check is a no-op, as before.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from backend import nudges as nudge_utils
from backend.auth import get_owner_check_identity
from backend.common.authz import ensure_owner_access
from backend.common.errors import PermissionDeniedError
from backend.routes._accounts import resolve_accounts_root

router = APIRouter(prefix="/nudges", tags=["nudges"])


class SubscribePayload(BaseModel):
    user: str
    frequency: int
    snooze_until: Optional[str] = None


@router.post("/subscribe")
def subscribe(payload: SubscribePayload, request: Request, identity: Optional[str] = Depends(get_owner_check_identity)):
    ensure_owner_access(identity, payload.user, resolve_accounts_root(request))
    nudge_utils.set_user_nudge(payload.user, payload.frequency, payload.snooze_until)
    return {"status": "ok"}


class SnoozePayload(BaseModel):
    user: str
    days: int = 1


@router.post("/snooze")
def snooze(payload: SnoozePayload, request: Request, identity: Optional[str] = Depends(get_owner_check_identity)):
    ensure_owner_access(identity, payload.user, resolve_accounts_root(request))
    nudge_utils.snooze_user(payload.user, payload.days)
    return {"status": "ok"}


def _visible_nudges(nudges: List[Dict], identity: Optional[str], request: Request) -> List[Dict]:
    """The nudges whose ``id`` (the nudge's user) the caller may act for, plus any without one.

    Each distinct user is checked once with :func:`ensure_owner_access`, the
    rule ``/subscribe`` and ``/snooze`` apply.
    """
    accounts_root = resolve_accounts_root(request)
    allowed: Dict[str, bool] = {}
    visible = []
    for nudge in nudges:
        user = nudge.get("id") if isinstance(nudge, dict) else None
        if not isinstance(user, str) or not user:
            visible.append(nudge)
            continue
        if user not in allowed:
            try:
                ensure_owner_access(identity, user, accounts_root)
                allowed[user] = True
            except PermissionDeniedError:
                allowed[user] = False
        if allowed[user]:
            visible.append(nudge)
    return visible


@router.get("/")
def list_nudges(request: Request, identity: Optional[str] = Depends(get_owner_check_identity)):
    return _visible_nudges(nudge_utils.get_recent_nudges(), identity, request)
