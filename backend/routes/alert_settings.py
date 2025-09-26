from __future__ import annotations

import inspect

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from backend import alerts as alert_utils
from backend.auth import get_active_user, get_current_user

DEMO_IDENTITY = "demo"

router = APIRouter(prefix="/alert-thresholds", tags=["alerts"])


class ThresholdPayload(BaseModel):
    threshold: float


def _validate_owner(user: str, current_user: str) -> None:
    """Ensure requests only act on the authenticated user's settings."""
    if user != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Owner mismatch"
        )


async def _resolve_identity(
    request: Request, current_user: str | None
) -> str:
    """Return the identity for the current request.

    The alert routes primarily rely on :func:`backend.auth.get_active_user` so
    that authentication can be disabled for demo environments.  The route
    tests, however, override :func:`backend.auth.get_current_user` directly.
    FastAPI's dependency override system only applies when the dependency is
    referenced explicitly in the signature, so ``get_current_user`` overrides
    would otherwise be ignored when auth is disabled and ``get_active_user``
    returns ``None``.  To support both behaviours we detect an override at
    runtime and defer to it when present.  This keeps the production behaviour
    unchanged while allowing the tests to inject an authenticated user without
    reconfiguring the app.
    """

    if current_user is not None:
        return current_user

    override = request.app.dependency_overrides.get(get_current_user)
    if override is not None:
        overridden = override()
        if inspect.isawaitable(overridden):
            overridden = await overridden
        if overridden is not None:
            return overridden

    return DEMO_IDENTITY


@router.get("/{user}")
async def get_threshold(
    user: str,
    request: Request,
    current_user: str | None = Depends(get_active_user),
):
    """Return the alert threshold configured for ``user``."""
    identity = await _resolve_identity(request, current_user)
    _validate_owner(user, identity)
    return {"threshold": alert_utils.get_user_threshold(identity)}


@router.post("/{user}")
async def set_threshold(
    user: str,
    payload: ThresholdPayload,
    request: Request,
    current_user: str | None = Depends(get_active_user),
):
    """Update the alert threshold for ``user``."""
    identity = await _resolve_identity(request, current_user)
    _validate_owner(user, identity)
    alert_utils.set_user_threshold(identity, payload.threshold)
    return {"threshold": payload.threshold}

