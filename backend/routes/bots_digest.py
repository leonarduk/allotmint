"""Read-only bots digest API (#10485).

* ``GET /bots/digest/{owner}/latest``: the latest stored digest.
* ``GET /bots/digest/{owner}/history``: stored digests, newest first.
* ``GET /bots/digest/{owner}/preview``: the digest as it would be composed now
  from the latest run records. Nothing is saved or sent.
* ``GET`` / ``PUT /bots/digest/{owner}/settings``: the owner's digest settings
  (period, channels, amounts, empty digests, per-bot cap and which bots alert
  immediately, #10502). ``PUT`` merges the given fields over the current ones.
  They belong to the owner, so owner access is enough; no admin needed.

Every route checks owner access (:func:`backend.common.authz.ensure_owner_access`;
the settings routes resolve the caller with
:func:`backend.auth.get_owner_check_identity`, as #11352's per-owner routes do).
System-wide items (``owner`` is ``None``, e.g. a failed scheduled job) are only
returned to admins: the deployment's configured owner emails, or anyone on a
local run without sign-in. The Lambda always runs with ``DISABLE_AUTH`` set
(API Gateway does the sign-in), so the email check still applies there (#11046).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import ValidationError

from backend.auth import get_active_user, get_owner_check_identity, is_demo_request
from backend.bots import digest_store
from backend.bots.digest import compose_digest
from backend.bots.digest_models import Digest
from backend.bots.digest_settings import DigestSettings, load_settings, save_settings
from backend.bots.registry import list_bots
from backend.bots.run_records import RegistryRunRecordSource
from backend.common.authz import ensure_owner_access
from backend.common.errors import raise_owner_not_found
from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bots/digest", tags=["bots"])


def is_admin(identity: Optional[str]) -> bool:
    if is_demo_request():
        return False
    if config.disable_auth and config.app_env == "local":
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


def _settings_errors(values: Dict[str, Any], merged: Dict[str, Any]) -> List[Dict[str, Any]]:
    """422 detail for unknown fields and unregistered bots, in the shape the Bots page shows."""

    errors = [
        {"loc": [key], "msg": "Unknown setting", "type": "extra_forbidden"}
        for key in sorted(set(values) - set(DigestSettings.model_fields))
    ]
    alerts = merged.get("alert_immediately_for")
    if isinstance(alerts, dict):
        known = {bot.id for bot in list_bots()}
        errors += [
            {"loc": ["alert_immediately_for", key], "msg": "Unknown bot", "type": "value_error"}
            for key in sorted(str(k) for k in alerts if k not in known)
        ]
    return errors


@router.get("/{owner}/settings")
def digest_settings(
    owner: str,
    request: Request,
    identity: Annotated[Optional[str], Depends(get_owner_check_identity)] = None,
):
    """The owner's digest settings (the defaults until any are saved)."""

    canonical = _resolve_owner(request, owner, identity)
    return load_settings(canonical).model_dump(mode="json")


@router.put("/{owner}/settings")
def update_digest_settings(
    owner: str,
    request: Request,
    values: Annotated[Dict[str, Any], Body()],
    identity: Annotated[Optional[str], Depends(get_owner_check_identity)] = None,
):
    """Validate and save the owner's digest settings (merged over the current ones); 422 on bad values."""

    canonical = _resolve_owner(request, owner, identity)
    current = load_settings(canonical).model_dump(mode="json")
    merged = {**current, **values}
    errors = _settings_errors(values, merged)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    try:
        settings = DigestSettings.model_validate(merged)
    except ValidationError as exc:
        detail = [
            {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type", "")}
            for err in exc.errors(include_url=False)
        ]
        raise HTTPException(status_code=422, detail=detail) from None
    save_settings(canonical, settings)
    after = settings.model_dump(mode="json")
    logger.info(
        "Digest settings for %s updated: %s",
        sanitise_log_value(canonical),
        sanitise_log_value(sorted(k for k in after if current.get(k) != after.get(k))),
    )
    return after
