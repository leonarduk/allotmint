"""Per-owner authorization helpers.

AllotMint uses a family/viewer access model: an authenticated identity may
access an owner's data when the identity matches the owner id, the owner's
configured ``email``, or appears in the owner's ``viewers`` list. This mirrors
the scoping already applied by :func:`backend.common.data_loader.list_plots`
for the ``/owners`` listing (see ``_is_authorized`` in ``_list_local_plots``),
and is applied here to per-owner endpoints that were previously authenticated
but not authorized (e.g. ``/user-config/<owner>`` and
``/accounts/<owner>/approvals``).

When ``config.disable_auth`` is truthy the API runs in local/demo mode where
the ``/owners`` listing exposes every owner and no identity is enforced; these
helpers deliberately no-op in that mode so demo and no-auth flows are not
restricted.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping, Optional, Set

from backend.common.data_loader import load_person_meta
from backend.common.errors import PermissionDeniedError
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

_FORBIDDEN_DETAIL = "Not authorized for this owner"


def _allowed_identities(owner: str, meta: Mapping[str, Any]) -> Set[str]:
    """Return the lower-cased identities permitted to access ``owner``."""

    allowed: Set[str] = set()
    if isinstance(owner, str) and owner.strip():
        allowed.add(owner.strip().lower())

    email = meta.get("email") if isinstance(meta, Mapping) else None
    if isinstance(email, str) and email.strip():
        allowed.add(email.strip().lower())

    viewers = meta.get("viewers") if isinstance(meta, Mapping) else None
    if isinstance(viewers, list):
        allowed.update(viewer.strip().lower() for viewer in viewers if isinstance(viewer, str) and viewer.strip())
    return allowed


def identity_can_access_owner(identity: Optional[str], owner: str, meta: Mapping[str, Any]) -> bool:
    """Return ``True`` when ``identity`` may access ``owner`` given ``meta``."""

    if not isinstance(identity, str) or not identity.strip():
        return False
    return identity.strip().lower() in _allowed_identities(owner, meta)


def ensure_owner_access(
    identity: Optional[str],
    owner: str,
    accounts_root: Optional[Path] = None,
) -> None:
    """Raise :class:`PermissionDeniedError` when ``identity`` lacks access.

    No-op when authentication is disabled (local/demo mode). Otherwise the
    owner's person metadata is consulted and the caller must match the owner
    id, the owner's email, or a listed viewer.

    Denials are logged (owner, whether an identity was present at all, and
    the allowed-identity set size) purely for diagnostics -- issue #5215
    reports a 403 here that couldn't be reproduced or root-caused from code
    alone; the next real occurrence should be traceable from these logs
    rather than requiring another blind investigation.
    """

    if config.disable_auth:
        return

    meta = load_person_meta(owner, accounts_root)
    if not identity_can_access_owner(identity, owner, meta):
        logger.warning(
            "ensure_owner_access denied: owner=%s identity_present=%s allowed_count=%s",
            sanitise_log_value(owner),
            identity is not None,
            len(_allowed_identities(owner, meta)),
        )
        raise PermissionDeniedError(_FORBIDDEN_DETAIL, safe_detail=_FORBIDDEN_DETAIL)
