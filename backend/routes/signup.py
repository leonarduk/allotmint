"""Public account-signup request endpoint.

Exposes ``POST /signup/request``: an unauthenticated endpoint that records a
visitor's interest in an account and emails the admin an approve/reject link.

Anti-enumeration: the handler performs no lookup against existing accounts and
always returns the same generic success body, so a caller cannot tell whether
an email already has an account. Only malformed payloads (bad shape) yield a
``400``; configuration/delivery failures yield ``5xx`` but reveal nothing about
account existence.
"""

from __future__ import annotations

import logging
import os
from json import JSONDecodeError
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.common import signup_requests
from backend.emails.signup_request import (
    SignupAdminNotification,
    send_signup_admin_email,
)
from backend.routes._accounts import resolve_accounts_root

router = APIRouter(prefix="/signup", tags=["signup"])

logger = logging.getLogger(__name__)

# Identical for every accepted request so the endpoint cannot be used to probe
# which emails already have accounts.
_GENERIC_OK: dict[str, str] = {
    "status": "ok",
    "message": "If your request is valid, an administrator has been notified.",
}


def _store_dir(request: Request) -> Path:
    """Return the writable directory for pending signup requests."""

    accounts_root = resolve_accounts_root(request, allow_missing=True)
    return signup_requests.signup_requests_dir(accounts_root.parent)


def _build_links(request_id: str, token: str) -> tuple[str, str]:
    """Build the approve/reject links consumed by the approval flow (#4352)."""

    base = os.getenv("SIGNUP_APPROVAL_BASE_URL", "").rstrip("/")
    query = f"id={request_id}&token={token}"
    return f"{base}/signup/approve?{query}", f"{base}/signup/reject?{query}"


@router.post("/request")
async def post_signup_request(request: Request) -> dict[str, str]:
    """Record a signup request and notify the admin; return a generic success."""

    try:
        payload = await request.json()
    except (JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid request body") from exc

    try:
        name, email, note = signup_requests.normalise_payload(payload)
    except signup_requests.SignupValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    admin_email = os.getenv("SIGNUP_ADMIN_EMAIL", "").strip()
    if not admin_email:
        # Misconfiguration, not a client error — and the same for every caller,
        # so it leaks nothing about account existence.
        logger.error("SIGNUP_ADMIN_EMAIL is not configured; cannot process signup requests")
        raise HTTPException(status_code=503, detail="signup is not available")

    record, token = signup_requests.create_signup_request(name, email, note, _store_dir(request))
    approve_url, reject_url = _build_links(record.id, token)
    notification = SignupAdminNotification(
        request_id=record.id,
        name=record.name,
        email=record.email,
        note=record.note,
        approve_url=approve_url,
        reject_url=reject_url,
        expires_at=record.expires_at,
    )

    try:
        send_signup_admin_email(admin_email, notification)
    except Exception as exc:  # noqa: BLE001 - surface any SES failure, never swallow it
        logger.exception("Failed to send signup admin email for request %s", record.id)
        raise HTTPException(status_code=502, detail="failed to notify administrator") from exc

    return dict(_GENERIC_OK)
