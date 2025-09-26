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
    request: Request,
    active_user: str | None = Depends(get_active_user),
) -> str:
    """Return the identity for the request, honouring test overrides.

    ``get_active_user`` returns ``None`` when authentication is disabled, in
    which case we fall back to ``DEMO_IDENTITY``.  The tests override
    :func:`backend.auth.get_current_user` to inject a specific identity so we
    check FastAPI's dependency overrides registry for a replacement callable
    and invoke it when present.  When auth is enabled both helpers return the
    same value and this function simply forwards it.
    """

    if active_user:
        return active_user

    override = request.app.dependency_overrides.get(get_current_user)
    if override:
        explicit_user = override()
        if inspect.isawaitable(explicit_user):
            explicit_user = await explicit_user
        if explicit_user:
            return explicit_user
    return DEMO_IDENTITY


@router.get("/{user}")
async def get_threshold(
    user: str,
    identity: str = Depends(_resolve_identity),
):
    """Return the alert threshold configured for ``user``."""
    _validate_owner(user, identity)
    return {"threshold": alert_utils.get_user_threshold(identity)}


@router.post("/{user}")
async def set_threshold(
    user: str,
    payload: ThresholdPayload,
    identity: str = Depends(_resolve_identity),
):
    """Update the alert threshold for ``user``."""
    _validate_owner(user, identity)
    alert_utils.set_user_threshold(identity, payload.threshold)
    return {"threshold": payload.threshold}

