"""Public account-signup request endpoint and admin approval flow.

Exposes:

* ``POST /signup/request`` — an unauthenticated endpoint that records a
  visitor's interest in an account and emails the admin an approve/reject link.
* ``/signup/approve`` and ``/signup/reject`` — the admin approval flow
  (#4352). The unguessable, single-use token from the admin email authorises
  the action, so these need no session auth. ``GET`` (a clicked email link)
  renders a side-effect-free confirmation page; the state change happens only
  on ``POST`` so link prefetchers cannot consume a token. Approving provisions
  the owner (adds their email to the login allowlist via ``person.json``) and
  emails the user that their login is ready.

Anti-enumeration: the request handler performs no lookup against existing
accounts and always returns the same generic success body, so a caller cannot
tell whether an email already has an account. Only malformed payloads (bad
shape) yield a ``400``; configuration/delivery failures yield ``5xx`` but
reveal nothing about account existence.

Rate limiting: when :func:`create_router` is given a ``slowapi.Limiter``,
``POST /signup/request`` is decorated with a per-IP rate limit (default
``"5/minute"``). The limiter is shared with the app-level instance so counters
are consistent across the whole application.
"""

from __future__ import annotations

import logging
import os
import warnings
from copy import deepcopy
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from markupsafe import escape

from backend.common import signup_provision, signup_requests
from backend.common.signup_requests import (
    RequestAlreadyProcessed,
    SignupTokenError,
)
from backend.emails.signup_approved import send_signup_approved_email
from backend.emails.signup_request import (
    SignupAdminNotification,
    send_signup_admin_email,
)
from backend.routes._accounts import resolve_accounts_root
from backend.routes.transactions import resolve_writable_store

if TYPE_CHECKING:
    from slowapi import Limiter

# WARNING: this module-level router has NO rate limiting applied. It exists
# for backward compatibility (tests and direct imports) only. Production code
# must call create_router(limiter=...) instead -- create_router(limiter=None)
# (its own default) also returns this same unprotected router, so passing a
# limiter is not optional for a production mount.
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
    """Build the approve/reject links consumed by the approval flow (#4352).

    Raises ``RuntimeError`` when ``SIGNUP_APPROVAL_BASE_URL`` is unset: a
    relative link is unusable in the emailed notification (email clients
    cannot resolve it), so failing loudly here beats silently sending the
    admin a broken link (#4369).
    """

    base = os.getenv("SIGNUP_APPROVAL_BASE_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("SIGNUP_APPROVAL_BASE_URL must be set")
    query = f"id={request_id}&token={token}"
    return f"{base}/signup/approve?{query}", f"{base}/signup/reject?{query}"


async def _post_signup_request_impl(request: Request) -> dict[str, str]:
    """Implementation of POST /signup/request — record and notify."""

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
    try:
        approve_url, reject_url = _build_links(record.id, token)
    except RuntimeError:
        # Misconfiguration, not a client error — and the same for every
        # caller, so it leaks nothing about account existence (matches the
        # SIGNUP_ADMIN_EMAIL check above).
        logger.error("SIGNUP_APPROVAL_BASE_URL is not configured; cannot build admin approval links")
        raise HTTPException(status_code=503, detail="signup is not available") from None
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


@router.post("/request")
async def post_signup_request(request: Request) -> dict[str, str]:
    """Record a signup request and notify the admin; return a generic success."""
    return await _post_signup_request_impl(request)


def _login_url() -> str:
    """Return the login page URL emailed to a newly approved user.

    Callers must check this is non-empty before using it (see
    ``approve_signup_request``) rather than silently emailing a linkless or
    fabricated URL — a misconfigured deployment should fail loudly, not send
    users to a broken link (#4385).
    """

    return os.getenv("SIGNUP_LOGIN_URL", "").strip()


def _token_error_to_http(exc: SignupTokenError) -> HTTPException:
    """Map a token-consumption failure to an unambiguous HTTP response.

    Not-found, bad-token, and expired all collapse to the same ``400`` so a
    caller cannot distinguish a wrong token from a missing/expired request
    (no enumeration of valid request ids). Already-processed is a distinct
    ``409`` so a replay is clearly — and safely — rejected.
    """

    if isinstance(exc, RequestAlreadyProcessed):
        return HTTPException(status_code=409, detail="this request has already been processed")
    return HTTPException(status_code=400, detail="invalid or expired approval token")


def _confirmation_page(action: str, request: Request, id: str, token: str) -> HTMLResponse:
    """Render a side-effect-free confirmation page for a clicked email link.

    ``GET`` must not mutate state: email clients and link scanners routinely
    prefetch links, which would otherwise consume a single-use token before the
    admin acts. The page validates the token read-only and presents a form that
    POSTs the actual action, so only a deliberate human click takes effect.
    """

    store_dir = _store_dir(request)
    try:
        record = signup_requests.validate_request(id, token, store_dir)
    except SignupTokenError as exc:
        body = f"<p>This request cannot be {action}d: {escape(_token_error_to_http(exc).detail)}.</p>"
        return HTMLResponse(f"<html><body>{body}</body></html>", status_code=400)

    verb = action.capitalize()
    page = (
        "<html><body>"
        f"<h2>{verb} access request</h2>"
        f"<p>Request from <strong>{escape(record.name)}</strong> "
        f"(<strong>{escape(record.email)}</strong>).</p>"
        f'<form method="post" action="/signup/{action}?id={escape(id)}&amp;token={escape(token)}">'
        f'<button type="submit">Confirm {action}</button>'
        "</form>"
        "</body></html>"
    )
    return HTMLResponse(page)


@router.get("/approve", response_class=HTMLResponse)
async def approve_signup_confirm(request: Request, id: str = "", token: str = "") -> HTMLResponse:
    """Show a confirmation page; the approval itself is performed by ``POST``."""

    return _confirmation_page("approve", request, id, token)


@router.post("/approve")
async def approve_signup_request(request: Request, id: str = "", token: str = "") -> dict[str, str]:
    """Provision the requesting user and notify them their login is ready.

    Validates the single-use token first, then provisions (idempotently) and
    only then consumes the token, so a transient provisioning failure does not
    burn the request. The user-notification email failure is surfaced rather
    than swallowed.
    """

    store_dir = _store_dir(request)
    try:
        record = signup_requests.validate_request(id, token, store_dir)
    except SignupTokenError as exc:
        raise _token_error_to_http(exc) from exc

    login_url = _login_url()
    if not login_url:
        # Misconfiguration, not a client error. Fail before provisioning so an
        # unset SIGNUP_LOGIN_URL never results in a linkless (or fabricated)
        # login email (#4385).
        logger.error("SIGNUP_LOGIN_URL is not configured; cannot approve signup requests")
        raise HTTPException(status_code=503, detail="signup approval is not available")

    accounts_root = resolve_accounts_root(request, allow_missing=True)
    store = resolve_writable_store(request)
    owner = signup_provision.provision_owner(record, accounts_root, store=store)

    # Burn the token only after provisioning succeeded. The returned record is
    # not needed here — the status flip is the side effect we want.
    try:
        _ = signup_requests.consume_request(id, token, store_dir, new_status="approved")
    except SignupTokenError as exc:  # pragma: no cover - lost race with another approver
        raise _token_error_to_http(exc) from exc

    try:
        send_signup_approved_email(record.email, record.name, login_url)
    except Exception as exc:  # noqa: BLE001 - surface any SES failure, never swallow it
        logger.exception("Failed to send login-ready email for request %s", record.id)
        raise HTTPException(status_code=502, detail="failed to notify user") from exc

    return {"status": "approved", "owner": owner}


@router.get("/reject", response_class=HTMLResponse)
async def reject_signup_confirm(request: Request, id: str = "", token: str = "") -> HTMLResponse:
    """Show a confirmation page; the rejection itself is performed by ``POST``."""

    return _confirmation_page("reject", request, id, token)


@router.post("/reject")
async def reject_signup_request(request: Request, id: str = "", token: str = "") -> dict[str, str]:
    """Mark a pending request rejected so its token can no longer be used."""

    store_dir = _store_dir(request)
    # The status flip is the side effect we want; the record is not needed.
    try:
        _ = signup_requests.consume_request(id, token, store_dir, new_status="rejected")
    except SignupTokenError as exc:
        raise _token_error_to_http(exc) from exc

    return {"status": "rejected"}


def create_router(
    limiter: "Limiter | None" = None,
    rate_limit: str | None = None,
) -> APIRouter:
    """Return a signup router, optionally with per-IP rate limiting.

    When ``limiter`` and ``rate_limit`` are provided, ``POST /signup/request``
    is decorated via ``limiter.limit(rate_limit)``. The limiter must be the
    same instance registered on ``app.state.limiter`` so rate-limit counters
    are shared across the application.

    If ``limiter`` is ``None`` (the default) or ``rate_limit`` is falsy, this
    returns the unprotected module-level ``router`` with no rate limiting at
    all -- always pass both for a production mount.

    Approve and reject endpoints are not rate-limited — they already require
    unguessable single-use tokens.
    """

    if limiter is None or not rate_limit:
        warnings.warn(
            "create_router() returned the unprotected signup router with no "
            "rate limiting on POST /signup/request -- pass both limiter and "
            "rate_limit for a production mount.",
            RuntimeWarning,
            stacklevel=2,
        )
        return router

    limited = APIRouter(prefix="/signup", tags=["signup"])

    # POST /request with rate limit
    limited_request = limiter.limit(rate_limit)(_post_signup_request_impl)
    limited.post("/request")(limited_request)

    # Other routes are copied from the module-level router without rate limits.
    # Deep-copy so mutating a route on `limited` can't corrupt the shared
    # module-level `router` (and vice versa).
    for route in router.routes:
        if getattr(route, "path", None) == "/request":
            continue  # already registered above with rate limit
        limited.routes.append(deepcopy(route))

    return limited
