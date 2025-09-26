from __future__ import annotations

from typing import Optional

from fastapi import Request

from backend.auth import get_current_user, oauth2_scheme
from backend.config import config as app_config


async def get_active_user(request: Request) -> Optional[str]:
    """Return the authenticated user or ``None`` when auth is disabled.

    The dependency intentionally skips OAuth processing when authentication
    has been disabled via configuration so routes can accept anonymous
    requests in demo environments. When auth remains enabled the helper
    mirrors :func:`backend.auth.get_current_user` but keeps the dependency
    signature free from ``Depends`` so callers can reuse it seamlessly.
    """

    if app_config.disable_auth:
        return None

    token = await oauth2_scheme(request)
    return await get_current_user(token)


__all__ = ["get_active_user"]
