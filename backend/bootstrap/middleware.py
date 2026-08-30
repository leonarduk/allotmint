"""Middleware and exception-handler registration for FastAPI bootstrap."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security.utils import get_authorization_scheme_param
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from backend.auth import _resolve_demo_request, decode_demo_token
from backend.auth import demo_readonly as demo_readonly_var
from backend.common.errors import AppError, log_app_error
from backend.config import Config
from backend.logging_setup import sanitise_log_value

_CORS_ALLOW_METHODS = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]
_CORS_ALLOW_HEADERS = [
    "Accept",
    "Authorization",
    "Content-Type",
    "Origin",
    "X-Requested-With",
]

logger = logging.getLogger(__name__)

# Safelist, never denylist (#7407): only these methods may ever be served to a
# demo-scoped request. Any other verb -- present or added in the future -- is
# rejected by this gate regardless of which router handles it.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_DEMO_WRITE_BLOCKED_DETAIL = "Demo access is read-only"


def normalize(obj: Any) -> Any:
    """Recursively convert bytes to strings for JSON serialization."""
    if isinstance(obj, bytes):
        return obj.decode(encoding="utf-8", errors="replace")
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize(v) for v in obj]
    return obj


def register_middleware(app: FastAPI, cfg: Config) -> None:
    """Register middleware, rate limiting, and request validation handling."""

    storage_uri = "memory://"
    if cfg.app_env in {"production", "aws"}:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            storage_uri = redis_url

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[f"{cfg.rate_limit_per_minute}/minute"],
        storage_uri=storage_uri,
    )
    app.state.limiter = limiter
    # slowapi's _rate_limit_exceeded_handler returns Response, but Starlette's
    # add_exception_handler expects Response | Awaitable[Response]. The handler
    # is compatible at runtime; slowapi lacks typed stubs that satisfy mypy.
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    default_cors = ["http://localhost:3000", "http://localhost:5173"]
    cors_origins = _validate_cors_origins(list(dict.fromkeys((cfg.cors_origins or []) + default_cors)))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=_CORS_ALLOW_METHODS,
        allow_headers=_CORS_ALLOW_HEADERS,
        allow_credentials=True,
    )
    app.add_middleware(SlowAPIMiddleware)

    @app.middleware("http")
    async def demo_scope_gate(request: Request, call_next):
        """Resolve a demo-scoped token's identity, and reject any non-safe
        HTTP method it carries.

        This is the global, deny-by-default enforcement point for #7402's
        read-only demo link. It has two jobs:

        1. **Resolve demo identity for every request (regression fix).**
           ``get_current_user``/``get_active_user`` (#7406) are what normally
           call ``_resolve_demo_request`` to set the ``current_user``/
           ``demo_readonly`` ContextVars that ``is_demo_request()`` (used by
           ``ensure_owner_access`` (#7408) and ``_list_aws_plots``/
           ``_list_local_plots``) depend on. But per-route authorization in
           this app is **not uniform**: many routers are registered with no
           router-level ``Depends(auth.get_current_user)`` at all when
           ``config.disable_auth`` is true (``protected = []`` in
           ``backend/bootstrap/routers.py`` -- true on every real AWS
           deployment, since API Gateway is the auth boundary there), and
           several route handlers -- e.g. ``GET /owners`` in its
           ``disable_auth`` branch, and everything behind
           ``GET /portfolio-group/{slug}`` -- never declare
           ``Depends(get_current_user)``/``get_active_user`` themselves
           either. For any such route, ``_resolve_demo_request`` was never
           being called at all, so ``is_demo_request()`` stayed ``False``
           and every owner-scoping check built on top of it was silently a
           no-op -- confirmed live: a minted demo-link token could read
           every real owner's full portfolio (including holdings) via the
           default "all owners" group dashboard and via ``GET /owners``,
           not just the configured demo owner. Resolving the identity here,
           unconditionally, closes that gap for every route regardless of
           its own dependency wiring, because middleware runs before FastAPI
           dispatches to any handler.
        2. **Block writes (#7407).** A single global method safelist check
           here is verifiable by inspection and cannot be skipped by a
           future route author, unlike per-route checks.

        Ordering and reset: ``demo_readonly`` is reset to ``False`` at the
        very top of *every* request, demo or not -- mirroring the same reset
        in ``get_current_user``/``get_active_user`` (see the ContextVar's
        docstring in ``backend/auth.py``) -- because a Lambda execution
        environment can be reused across invocations, and this middleware is
        now the only place guaranteed to run for every request. Leaving a
        previous request's ``True`` in place would leak a demo-scoped
        identity into a later, unrelated request that also happens not to
        invoke ``get_current_user``/``get_active_user``.

        This independently decodes the raw ``Authorization`` bearer token
        with :func:`backend.auth.decode_demo_token` / calls
        :func:`backend.auth._resolve_demo_request` directly, exactly as
        ``get_current_user``/``get_active_user`` do, rather than waiting for
        FastAPI's dependency resolution (which runs *after* middleware and,
        per above, may not run at all for a given route). Both checks below
        are intentionally independent of ``config.disable_auth`` -- a
        syntactically valid demo-scoped token (one signed with this
        process's own ``SECRET_KEY``) must be identified and confined under
        any configuration. ``_resolve_demo_request`` itself still separately
        enforces ``config.demo_link_enabled`` and the ``demo_link_owner``
        match, raising 401 for a disabled or mismatched token.
        """

        demo_readonly_var.set(False)

        auth_header = request.headers.get("Authorization")
        scheme, token = get_authorization_scheme_param(auth_header)
        is_demo_token = bool(token and scheme.lower() == "bearer" and decode_demo_token(token) is not None)

        if is_demo_token and request.method not in _SAFE_METHODS:
            logger.warning(
                "Blocked non-safe method on demo-scoped request: method=%s path=%s",
                sanitise_log_value(request.method),
                sanitise_log_value(request.url.path),
            )
            return JSONResponse(
                status_code=403,
                content={"detail": _DEMO_WRITE_BLOCKED_DETAIL},
            )

        # OPTIONS (CORS preflight) is deliberately excluded from identity
        # resolution, not just the write-block above: browsers never attach
        # real credentials to a preflight, and API Gateway's own OPTIONS
        # routes are unauthenticated for the same reason (see
        # cdk/stacks/backend_lambda_stack.py). Resolving -- and potentially
        # 401-ing -- a preflight based on demo_link_enabled/owner state would
        # break CORS for reasons entirely unrelated to the real request.
        if is_demo_token and request.method != "OPTIONS":
            try:
                _resolve_demo_request(token)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        return await call_next(request)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        log_app_error(
            logging.getLogger("backend.errors"),
            exc,
            "Request failed",
            path=str(request.url.path),
            method=request.method,
        )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.safe_detail})

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError):
        status = 422 if exc.body is not None else 400
        return JSONResponse(status_code=status, content={"detail": _sanitize_error_details(exc.errors())})


def _validate_cors_origins(origins: list[str]) -> list[str]:
    """Ensure each origin uses http(s) and has a concrete host."""
    validated: list[str] = []
    for origin in origins:
        parsed = urlparse(origin)
        if parsed.scheme in {"http", "https"} and parsed.netloc and "*" not in parsed.netloc:
            validated.append(origin)
        else:
            raise ValueError(f"Invalid CORS origin: {origin}")
    return validated


def _sanitize_error_details(error: Any) -> Any:
    if isinstance(error, dict):
        return {k: _sanitize_error_details(v) for k, v in error.items()}
    if isinstance(error, (list, tuple)):
        return [_sanitize_error_details(item) for item in error]
    if isinstance(error, bytes):
        return error.decode("utf-8", errors="replace")
    return error
