"""The signed-in user's named watchlists (#10713).

``GET /watchlists`` returns the saved watchlists and ``PUT /watchlists``
replaces them, naming the revision the change was based on; a stale revision
is a 409 carrying the current copy. Every handler is keyed by the
authenticated user, so a caller can only reach their own watchlists; storage
lives in :mod:`backend.common.watchlists`.

Demo sessions are read-only and share one identity across visitors, so they
read nothing saved and are refused (403) every write. So is a caller with no
identity at all (auth disabled and no local login override): ``owner`` is null
and the browser keeps its lists to itself. That case answers 200, not 401,
because a 401 makes the SPA sign the user out.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from backend.auth import get_active_user, is_demo_request
from backend.common import watchlists
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watchlists", tags=["watchlists"])

# The largest allowed document (50 lists of 2,000 symbols) is well under this.
MAX_DOCUMENT_BYTES = 2_000_000

CODE_CONFLICT = "watchlists_conflict"
CODE_UNAVAILABLE = "watchlists_unavailable"


class WatchlistsPut(BaseModel):
    revision: int = Field(ge=0)
    state: watchlists.WatchlistsState


def _unavailable(exc: watchlists.WatchlistsUnavailable) -> JSONResponse:
    logger.warning("Watchlists store unavailable: %s", sanitise_log_value(exc))
    return JSONResponse(
        status_code=503,
        content={"detail": "Watchlist storage is unavailable", "code": CODE_UNAVAILABLE},
    )


def _conflict(exc: watchlists.WatchlistsConflict) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": "The watchlists were changed in another tab or device",
            "code": CODE_CONFLICT,
            "current": exc.current,
        },
    )


async def _parse_put(request: Request) -> WatchlistsPut:
    # Refuse a declared oversize body before reading it into memory.
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Watchlists are too large to save")
    body = await request.body()
    if len(body) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Watchlists are too large to save")
    try:
        return WatchlistsPut.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False, include_context=False)) from exc


@router.get("")
def get_watchlists(user: Optional[str] = Depends(get_active_user)):
    """The saved watchlists (``state`` is null until first saved), plus ``owner``.

    ``owner`` is an opaque id for the caller. The browser keeps it with its
    local copy, so after a change of identity it can tell whose watchlists it
    is holding and never uploads one user's cached lists into another account.
    """

    if not user:
        return {"owner": None, "revision": 0, "state": None}
    owner = watchlists.user_key(user)
    if is_demo_request():
        return {"owner": owner, "revision": 0, "state": None}
    try:
        return {"owner": owner, **watchlists.load_watchlists(user)}
    except watchlists.WatchlistsUnavailable as exc:
        return _unavailable(exc)


@router.put("")
async def put_watchlists(request: Request, user: Optional[str] = Depends(get_active_user)):
    if is_demo_request():
        raise HTTPException(status_code=403, detail="Demo sessions cannot save watchlists")
    if not user:
        raise HTTPException(status_code=403, detail="Sign in to save watchlists")
    payload = await _parse_put(request)
    try:
        revision = watchlists.save_watchlists(user, payload.state, payload.revision)
    except watchlists.WatchlistsConflict as exc:
        return _conflict(exc)
    except watchlists.WatchlistsUnavailable as exc:
        return _unavailable(exc)
    return {"revision": revision, "state": payload.state.model_dump()}
