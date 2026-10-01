"""Admin-identity check shared by routes that need an admin-only gate."""

from __future__ import annotations

import os
from typing import Optional

from backend.config import config


def is_admin_identity(identity: Optional[str]) -> bool:
    """Return ``True`` when ``identity`` may perform admin-only actions.

    Mirrors ``require_admin`` in ``backend/app.py``: with an ``ADMIN_EMAILS``
    allowlist configured it is always enforced (even when ``disable_auth`` is
    set, as on the Lambda); with no allowlist only local dev
    (``disable_auth``) is allowed through.
    """

    raw = os.getenv("ADMIN_EMAILS", "")
    admins = {e.strip().lower() for e in raw.split(",") if e.strip()}
    if admins:
        return isinstance(identity, str) and identity.strip().lower() in admins
    return bool(config.disable_auth)
