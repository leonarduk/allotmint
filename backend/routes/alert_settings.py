from __future__ import annotations

import inspect
import logging
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from backend import alerts as alert_utils
from backend.auth import get_active_user, get_current_user

DEMO_IDENTITY = "demo"

router = APIRouter(prefix="/alert-thresholds", tags=["alerts"])

logger = logging.getLogger(__name__)


class ThresholdPayload(BaseModel):
    threshold: float


def _validate_owner(user: str, current_user: str) -> None:
    """Ensure requests only act on the authenticated user's settings."""
    if user != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Owner mismatch"
        )


@router.get("/{user}")
async def get_threshold(
    user: str,
    request: Request,
    current_user: str | None = Depends(get_active_user),
):
    """Return the alert threshold configured for ``user``."""
    identity = await _resolve_identity(user, request, current_user)

    try:
        threshold = alert_utils.get_user_threshold(identity)
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Failed to fetch alert threshold for %s", identity)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch alert threshold",
        ) from exc

    return {"threshold": threshold}


@router.post("/{user}")
async def set_threshold(
    user: str,
    payload: ThresholdPayload,
    request: Request,
    current_user: str | None = Depends(get_active_user),
):
    """Update the alert threshold for ``user``."""
    identity = await _resolve_identity(user, request, current_user)

    try:
        alert_utils.set_user_threshold(identity, payload.threshold)
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("Failed to update alert threshold for %s", identity)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update alert threshold",
        ) from exc

    return {"threshold": payload.threshold}


async def _resolve_identity(
    user: str,
    request: Request,
    active_user: str | None,
) -> str:
    """Return the identity associated with ``user`` considering overrides."""

    identity = active_user

    if identity is None:
        override = request.app.dependency_overrides.get(get_current_user)
        if override is not None:
            identity = await _call_override(override)

    identity = identity or DEMO_IDENTITY
    _validate_owner(user, identity)
    return identity


async def _call_override(override: Callable[[], Any]) -> Any:
    """Execute a dependency override, awaiting when required."""

    result = override()
    if inspect.isawaitable(result):
        result = await result
    return result

