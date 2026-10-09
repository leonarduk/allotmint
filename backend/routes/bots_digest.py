"""Read-only bots digest API (#10485).

* ``GET /bots/digest/{owner}/latest``: the latest stored digest.
* ``GET /bots/digest/{owner}/history``: stored digests, newest first.
* ``GET /bots/digest/{owner}/preview``: the digest as it would be composed now
  from the latest run records. Nothing is saved or sent.

Every route checks owner access (:func:`backend.common.authz.ensure_owner_access`).
System-wide items (``owner`` is ``None``, e.g. a failed scheduled job) are only
returned to admins: the deployment's configured owner emails, or anyone when
auth is disabled, the same gate as ``backend/routes/mcp_server_admin.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.auth import get_active_user
from backend.bots import digest_store
from backend.bots.digest import compose_digest
from backend.bots.digest_models import Digest
from backend.bots.digest_settings import load_settings
from backend.bots.run_records import RegistryRunRecordSource
from backend.common.authz import ensure_owner_access
from backend.common.errors import raise_owner_not_found
from backend.config import config
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory

router = APIRouter(prefix="/bots/digest", tags=["bots"])


def is_admin(identity: Optional[str]) -> bool:
    if config.disable_auth:
        return True
    allowed = {e.strip().lower() for e in (config.allowed_emails or []) if isinstance(e, str) and e.strip()}
    return identity is not None and identity.strip().lower() in allowed


def _resolve_owner(request: Request, owner: str, identity: Optional[str]) -> str:
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if owner_dir is None:
        raise_owner_not_found(owner)
    assert owner_dir is not None  # raise_owner_not_found always raises; narrows the type for mypy
    ensure_owner_access(identity, owner_dir.name, accounts_root)
    return owner_dir.name


def _scoped(digest: Digest, admin: bool) -> Dict[str, Any]:
    """The digest as JSON, without system-wide items for non-admins."""

    if not admin:
        digest = digest.model_copy(
            update={
                "items": [i for i in digest.items if i.owner is not None],
                "resolved": [i for i in digest.resolved if i.owner is not None],
            }
        )
    body = digest.model_dump(mode="json", exclude={"open_keys"})
    body["needs_owner"] = bool(body["items"])
    return body


@router.get("/{owner}/latest")
def latest_digest(owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)):
    canonical = _resolve_owner(request, owner, identity)
    digest = digest_store.load_latest(canonical)
    if digest is None:
        raise HTTPException(status_code=404, detail=f"No bots digest yet for {canonical}")
    return _scoped(digest, is_admin(identity))


@router.get("/{owner}/history")
def digest_history(
    owner: str,
    request: Request,
    limit: int = Query(8, ge=1, le=52),
    identity: Optional[str] = Depends(get_active_user),
):
    canonical = _resolve_owner(request, owner, identity)
    admin = is_admin(identity)
    return {"digests": [_scoped(d, admin) for d in digest_store.load_history(canonical, limit)]}


@router.get("/{owner}/preview")
def preview_digest(owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)):
    canonical = _resolve_owner(request, owner, identity)
    admin = is_admin(identity)
    settings = load_settings(canonical)
    digest = compose_digest(
        canonical,
        RegistryRunRecordSource(),
        previous=digest_store.load_latest(canonical),
        now=datetime.now(timezone.utc),
        include_system=admin,
        per_bot_cap=settings.per_bot_cap,
        period=settings.period,
    )
    return _scoped(digest, admin)
