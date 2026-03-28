"""Middleware and exception-handler registration for FastAPI bootstrap."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from backend.common.errors import AppError, log_app_error
from backend.config import Config

_CORS_ALLOW_METHODS = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]
_CORS_ALLOW_HEADERS = [
    "Accept",
    "Authorization",
    "Content-Type",
    "Origin",
    "X-Requested-With",
]


def normalize(obj: Any) -> Any:
    """Recursively convert bytes to strings for JSON serialization."""
    if isinstance(obj, bytes):
        return obj.decode("utf-8")
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
    cors_origins = _validate_cors_origins(
        list(dict.fromkeys((cfg.cors_origins or []) + default_cors))
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=_CORS_ALLOW_METHODS,
        allow_headers=_CORS_ALLOW_HEADERS,
        allow_credentials=True,
    )
    app.add_middleware(SlowAPIMiddleware)

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
        return JSONResponse(
            status_code=status, content={"detail": _sanitize_error_details(exc.errors())}
        )


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
