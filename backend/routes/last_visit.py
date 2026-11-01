"""The signed-in user's last visit to a group dashboard (#11195).

``POST /last-visit/{slug}`` records a visit now and returns the advanced
record (``previous`` is the visit the digest compares against, null on a
first visit); ``POST /last-visit/{slug}/dismiss`` marks everything up to now
as seen. Both are keyed by the authenticated user, so a caller only ever
reads or moves their own record; storage lives in
:mod:`backend.common.last_visit`.

A visit is recorded by the server rather than read and written back by the
browser, so two devices or tabs cannot interleave a read-modify-write.

Demo sessions share one identity across visitors, and a caller with no
identity (auth disabled, no local login override) has no user to key on:
both get ``stored: false`` with a 200, never a write, and the browser keeps
its own ``localStorage`` record instead. That case is not a 401 because a 401
makes the SPA sign the user out.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.auth import get_active_user, is_demo_request
from backend.common import last_visit
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/last-visit", tags=["last-visit"])

CODE_UNAVAILABLE = "last_visit_unavailable"
# Group and owner slugs; never a path, but bounded so the document stays small.
_SLUG_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$"

NOT_STORED = {"stored": False, "previous": None, "current": None}


class SeedIn(BaseModel):
    """The browser's old ``localStorage`` record, as ISO 8601 instants."""

    previous: Optional[str] = Field(default=None, max_length=64)
    current: str = Field(max_length=64)


class VisitIn(BaseModel):
    seed: Optional[SeedIn] = None


def _unavailable(exc: last_visit.LastVisitUnavailable) -> JSONResponse:
    logger.warning("Last-visit store unavailable: %s", sanitise_log_value(exc))
    return JSONResponse(
        status_code=503,
        content={"detail": "Last-visit storage is unavailable", "code": CODE_UNAVAILABLE},
    )


def _storable_user(user: Optional[str]) -> Optional[str]:
    """The caller's identity when their visits may be stored (signed in, not a demo session), else None."""
    return user if user and not is_demo_request() else None


@router.post("/{slug}")
def record_visit(
    body: Optional[VisitIn] = None,
    slug: str = Path(pattern=_SLUG_PATTERN),
    user: Optional[str] = Depends(get_active_user),
):
    email = _storable_user(user)
    if email is None:
        return NOT_STORED
    seed = body.seed.model_dump() if body and body.seed else None
    try:
        record = last_visit.record_visit(email, slug, seed=seed)
    except last_visit.LastVisitUnavailable as exc:
        return _unavailable(exc)
    return {"stored": True, **record.public()}


@router.post("/{slug}/dismiss")
def dismiss_visit(
    slug: str = Path(pattern=_SLUG_PATTERN),
    user: Optional[str] = Depends(get_active_user),
):
    email = _storable_user(user)
    if email is None:
        return NOT_STORED
    try:
        record = last_visit.dismiss_visit(email, slug)
    except last_visit.LastVisitUnavailable as exc:
        return _unavailable(exc)
    return {"stored": True, **record.public()}
