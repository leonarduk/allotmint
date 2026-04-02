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

from fastapi import FastAPI, HTTPException, Request

import backend.auth as auth
from backend.common.portfolio_utils import (
    _load_snapshot,
    refresh_snapshot_async,
    refresh_snapshot_in_memory,
)
from backend.bootstrap import (
    AppLifecycleService,
    configure_runtime_paths,
    load_runtime_config,
    register_middleware,
    register_routers,
)
from backend.config import reload_config

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

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
        docs_url="/docs",
        lifespan=lifespan,
    )
    app.state.background_tasks = []
    app.state.repo_root = runtime_paths.paths.repo_root
    app.state.accounts_root = runtime_paths.accounts_root
    app.state.accounts_root_is_global = runtime_paths.accounts_root_is_global
    app.state.virtual_pf_root = runtime_paths.paths.virtual_pf_root

    register_middleware(app, cfg)
    register_routers(app, cfg)

    @app.post("/token")
    async def login(request: Request):
        """Handle both JSON (id_token) and form (username/password) authentication."""
        id_token: str | None = None
        username: str | None = None

        content_type = request.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            payload = await request.json()
            if isinstance(payload, dict):
                token_candidate = payload.get("id_token")
                if isinstance(token_candidate, str):
                    id_token = token_candidate
        elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form_data = await request.form()
            username_raw = form_data.get("username")
            if isinstance(username_raw, str):
                username = username_raw
            token_raw = form_data.get("id_token")
            if isinstance(token_raw, str):
                id_token = token_raw

        if username is not None:
            if cfg.disable_auth or os.getenv("TESTING"):
                email = "user@example.com"
            else:
                raise HTTPException(status_code=400, detail="Password auth not supported in production")
        elif id_token:
            try:
                email = auth.authenticate_user(id_token)
            except HTTPException as exc:
                logger.warning("User authentication failed: %s", exc.detail)
                raise
        elif cfg.disable_auth:
            email = "user@example.com"
        else:
            raise HTTPException(status_code=400, detail="Missing credentials")

        if not email:
            logger.warning("authenticate_user returned no email")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        allowlist_raw = getattr(cfg, "allowed_emails", None)
        if allowlist_raw and not (cfg.disable_auth or os.getenv("TESTING")):
            normalized = {item.strip().lower() for item in allowlist_raw if isinstance(item, str) and item.strip()}
            if normalized and email.lower() not in normalized:
                logger.warning("Email %s not authorized for login", email)
                raise HTTPException(status_code=403, detail="email not authorized")

        token = auth.create_access_token(email)
        return {"access_token": token, "token_type": "bearer"}

    @app.post("/token/google")
    async def google_token(payload: dict):
        token = payload.get("token")
        if cfg.disable_auth:
            email = "user@example.com"
        else:
            if not token:
                raise HTTPException(status_code=400, detail="Missing token")
            try:
                email = auth.verify_google_token(token)
            except HTTPException as exc:
                logger.warning("Google token verification failed: %s", exc.detail)
                raise
        jwt_token = auth.create_access_token(email)
        return {"access_token": jwt_token, "token_type": "bearer"}

    @app.get("/health")
    async def health():
        """Return a small payload used by tests and uptime monitors."""

        return {"status": "ok", "env": cfg.app_env}

    return app


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=reload_config().uvicorn_port or 8000,
    )
