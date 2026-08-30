"""Backend application entry-point.

This module exposes :func:`create_app`, a small factory that builds and
configures the FastAPI instance used by both the local development server
(`uvicorn`) and the AWS Lambda handler. Keeping the setup in a function makes
it easy for tests to create isolated apps and mirrors the pattern recommended
by FastAPI.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import backend.auth as auth
from backend.bootstrap import (
    AppLifecycleService,
    configure_runtime_paths,
    load_runtime_config,
    register_middleware,
    register_routers,
)
from backend.common.core_optional import CoreFeatureUnavailableError
from backend.config import reload_config
from backend.integrations.moneyhub_api import MoneyhubNotConfiguredError
from backend.logging_setup import sanitise_log_value, setup_logging

logger = logging.getLogger(__name__)


class CognitoTokenRequest(BaseModel):
    id_token: str
    client_id: str


class DemoLinkResponse(BaseModel):
    token: str
    expires_at: datetime
    owner: str


async def moneyhub_not_configured_handler(_request: Request, exc: MoneyhubNotConfiguredError) -> JSONResponse:
    """Return a consistent service-unavailable response for Moneyhub routes."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})


async def core_feature_unavailable_handler(_request: Request, exc: CoreFeatureUnavailableError) -> JSONResponse:
    """Return a consistent payment-required response for allotmint-pro-only routes."""
    return JSONResponse(status_code=402, content={"detail": str(exc)})


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    setup_logging()

    cfg = load_runtime_config()
    runtime_paths = configure_runtime_paths(cfg)
    lifecycle = AppLifecycleService(cfg=cfg, temp_dirs=runtime_paths.temp_dirs)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await lifecycle.startup(app)
        yield
        await lifecycle.shutdown(app)

    app = FastAPI(
        title="Allotmint API",
        version="1.0",
        docs_url=None,
        lifespan=lifespan,
    )
    app.add_exception_handler(MoneyhubNotConfiguredError, moneyhub_not_configured_handler)
    app.add_exception_handler(CoreFeatureUnavailableError, core_feature_unavailable_handler)

    admin_emails_raw = os.getenv("ADMIN_EMAILS", "")
    admin_set: frozenset[str] = (
        frozenset(e.strip().lower() for e in admin_emails_raw.split(",") if e.strip())
        if admin_emails_raw.strip()
        else frozenset()
    )
    if not admin_set and not cfg.disable_auth:
        logger.warning(
            "ADMIN_EMAILS is not configured — /api-console will be inaccessible. "
            "Set ADMIN_EMAILS to a comma-separated list of admin emails."
        )

    async def require_admin(
        current_user: str | None = Depends(auth.get_active_user),
    ) -> str | None:
        if admin_set:
            # Allowlist is configured: always enforce it regardless of disable_auth.
            # DISABLE_AUTH=true is set on the Lambda because API Gateway handles Cognito
            # auth — it must NOT be used to bypass the admin restriction here.
            if current_user is None or current_user.lower() not in admin_set:
                raise HTTPException(status_code=403, detail="Admin access required")
        elif not cfg.disable_auth:
            # No allowlist in a production-like environment: deny all to avoid silent
            # misconfiguration letting everyone in.
            raise HTTPException(status_code=403, detail="Admin access required")
        # else: no allowlist + disable_auth → local dev, allow through
        return current_user

    app.state.background_tasks = []
    app.state.repo_root = runtime_paths.paths.repo_root
    app.state.accounts_root = runtime_paths.accounts_root
    app.state.accounts_root_is_global = runtime_paths.accounts_root_is_global
    app.state.virtual_pf_root = runtime_paths.paths.virtual_pf_root

    register_middleware(app, cfg)
    register_routers(app, cfg)

    @app.post(
        "/token",
        openapi_extra={
            "requestBody": {
                "required": False,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"id_token": {"type": "string"}},
                        }
                    },
                    "application/x-www-form-urlencoded": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "username": {"type": "string"},
                                "password": {"type": "string"},
                            },
                        }
                    },
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "username": {"type": "string"},
                                "password": {"type": "string"},
                            },
                        }
                    },
                },
            }
        },
    )
    async def login(request: Request):
        """Handle both JSON (id_token) and form (username/password) authentication."""
        id_token: str | None = None
        username: str | None = None

        content_type = request.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            try:
                payload = await request.json()
            except (JSONDecodeError, UnicodeDecodeError) as exc:
                raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="Invalid JSON body")

            if "id_token" in payload:
                token_candidate = payload.get("id_token")
                if not isinstance(token_candidate, str) or not token_candidate.strip():
                    raise HTTPException(status_code=400, detail="Invalid id_token")
                id_token = token_candidate
        elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form_data = await request.form()
            username_raw = form_data.get("username")
            if isinstance(username_raw, str):
                username = username_raw

        if username is not None:
            if cfg.disable_auth or os.getenv("TESTING"):
                email = auth.DISABLE_AUTH_STUB_EMAIL
            else:
                raise HTTPException(status_code=400, detail="Password auth not supported in production")
        elif id_token:
            try:
                email = auth.authenticate_user(id_token)
            except HTTPException as exc:
                logger.warning("User authentication failed: %s", sanitise_log_value(exc.detail))
                raise
        elif cfg.disable_auth:
            email = auth.DISABLE_AUTH_STUB_EMAIL
        else:
            raise HTTPException(status_code=400, detail="Missing credentials")

        if not email:
            logger.warning("authenticate_user returned no email")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        allowlist_raw = getattr(cfg, "allowed_emails", None)
        if allowlist_raw and not (cfg.disable_auth or os.getenv("TESTING")):
            normalized = {item.strip().lower() for item in allowlist_raw if isinstance(item, str) and item.strip()}
            if normalized and email.lower() not in normalized:
                logger.warning("Email %s not authorized for login", sanitise_log_value(email))
                raise HTTPException(status_code=403, detail="email not authorized")

        token = auth.create_access_token(email)
        return {"access_token": token, "token_type": "bearer"}

    @app.post("/token/google")
    async def google_token(payload: dict):
        token = payload.get("token")
        if cfg.disable_auth:
            email = auth.DISABLE_AUTH_STUB_EMAIL
        else:
            if not token:
                raise HTTPException(status_code=400, detail="Missing token")
            try:
                email = auth.verify_google_token(token)
            except HTTPException as exc:
                logger.warning("Google token verification failed: %s", sanitise_log_value(exc.detail))
                raise
        jwt_token = auth.create_access_token(email)
        return {"access_token": jwt_token, "token_type": "bearer"}

    @app.post("/token/cognito")
    async def cognito_token(payload: CognitoTokenRequest):
        token = payload.id_token
        client_id = payload.client_id
        if cfg.disable_auth:
            email = auth.DISABLE_AUTH_STUB_EMAIL
        else:
            if not isinstance(token, str) or not token:
                raise HTTPException(status_code=400, detail="Missing ID token")
            if not isinstance(client_id, str) or not client_id:
                raise HTTPException(status_code=400, detail="Missing client ID")
            try:
                email = auth.verify_cognito_token(token, client_id)
            except HTTPException as exc:
                logger.warning("Cognito token verification failed: %s", sanitise_log_value(exc.detail))
                raise
        jwt_token = auth.create_access_token(email)
        return {"access_token": jwt_token, "token_type": "bearer"}

    @app.get("/health")
    async def health():
        """Return a small payload used by tests and uptime monitors."""

        return {"status": "ok", "env": cfg.app_env}

    @app.get("/whoami")
    async def whoami(
        _: str | None = Depends(require_admin),
        token: str | None = Depends(auth.oauth2_scheme),
    ):
        """Auth-boundary debug view of the bearer token the backend received.

        Admin-gated (via ``require_admin`` / ``ADMIN_EMAILS``) so decoded claims
        are never exposed to non-admins. Returns whether a token was presented,
        an allowlisted subset of its claims (sub, email, exp, iss, token_use,
        aud), and whether its email matches the backend allowed-emails set.

        The ``_`` parameter is ``str | None`` (not ``str``) because
        ``require_admin`` returns ``None`` in local dev: when ``ADMIN_EMAILS``
        is unset and ``disable_auth`` is true, ``require_admin`` allows the
        request through without an authenticated user rather than raising, so
        this endpoint can be exercised without Cognito configured locally.
        In any other environment (an allowlist configured, or auth not
        disabled) ``require_admin`` raises 403 before ``_`` could be ``None``.

        Limitation: when the API Gateway Cognito JWT authorizer rejects a
        request it never reaches the Lambda, so this endpoint cannot diagnose
        gateway-level 401s — those are visible in API Gateway access logs in
        CloudWatch. See docs/AUTH.md.
        """

        result = auth.describe_token(token)
        result["note"] = (
            "Diagnoses backend token handling only. Gateway-rejected requests "
            "never reach this endpoint; see API Gateway access logs in CloudWatch."
        )
        return result

    @app.post("/demo-link", response_model=DemoLinkResponse)
    @app.state.limiter.limit(cfg.demo_link_mint_rate_limit)
    async def mint_demo_link(
        request: Request,
        _: str | None = Depends(require_admin),
    ) -> DemoLinkResponse:
        """Mint a short-lived, read-only demo-scoped token (#7402, step 6/9).

        Gated by **two independent checks**, both required:

        1. ``Depends(require_admin)`` -- exactly as ``/whoami`` and
           ``/api-console`` above. Note its documented local-dev quirk: with
           no ``ADMIN_EMAILS`` configured and ``disable_auth`` true it lets
           the request through with ``current_user is None``. That is
           acceptable for a read-only debug view but is not acceptable for a
           token mint on a deployed box, so this endpoint *additionally*
           requires (2) below -- a deployment that has not explicitly opted
           into the demo link stays refused regardless of the admin-gate's
           local-dev behaviour.
        2. ``config.demo_link_enabled`` -- the same master kill switch
           ``auth._resolve_demo_request``/``ensure_owner_access`` already
           enforce when a demo token is *used* (#7406/#7408). When it is
           false this endpoint returns 404 rather than minting anyway, so a
           deployment that has not turned the feature on does not even
           reveal that a mint endpoint exists.

        Returns 503 when ``config.demo_link_owner`` is unset -- rather than
        minting a token scoped to an empty owner -- since an operator must
        designate exactly one demo owner before this endpoint is usable.

        Rate-limited per ``config.demo_link_mint_rate_limit`` (default
        ``5/minute``, mirroring ``config.signup_rate_limit``'s pattern):
        minting produces something an unauthenticated visitor can later use,
        so even an authenticated admin should not be able to refresh it at
        an unbounded rate.

        Revocation: there is no per-token revocation. A minted token stays
        valid until it either (a) reaches its own ``exp``
        (``config.demo_link_ttl_hours`` after minting), (b) is refused going
        forward because ``config.demo_link_enabled`` was flipped to false
        (an already-issued, unexpired token then fails the
        ``demo_link_enabled``/owner checks in ``get_current_user``/
        ``get_active_user`` and ``ensure_owner_access``), or (c)
        ``JWT_SECRET`` is rotated -- which also invalidates every real
        user's backend JWT. There is no narrower way to kill one specific
        leaked link short of one of those three; an operator relying on
        this endpoint should know that going in.
        """

        if not cfg.demo_link_enabled:
            raise HTTPException(status_code=404, detail="Not Found")

        owner = cfg.demo_link_owner
        if not isinstance(owner, str) or not owner.strip():
            raise HTTPException(status_code=503, detail="Demo link owner is not configured")
        owner = owner.strip()

        token = auth.create_demo_access_token(owner, timedelta(hours=cfg.demo_link_ttl_hours))
        # Decode the freshly-minted token's own `exp` (rather than
        # independently recomputing `now + ttl`) so the returned expiry is
        # exactly what the token itself carries -- never logged, never
        # echoed anywhere but this response body.
        claims = jwt.decode(
            token,
            auth.SECRET_KEY,
            algorithms=[auth.ALGORITHM],
            options={"require": ["exp"]},
        )
        expires_at = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)

        logger.info(
            "Minted demo-link token for owner=%s ttl_hours=%s",
            sanitise_log_value(owner),
            sanitise_log_value(cfg.demo_link_ttl_hours),
        )

        return DemoLinkResponse(token=token, expires_at=expires_at, owner=owner)

    @app.get("/api-console", response_class=HTMLResponse, include_in_schema=False)
    async def api_console(_: str = Depends(require_admin)):
        """Interactive API console — restricted to admin users."""

        return get_swagger_ui_html(openapi_url="/openapi.json", title="Allotmint API Console")

    return app


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=reload_config().uvicorn_port or 8000,
    )
