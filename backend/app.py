"""Backend application entry-point.

This module exposes :func:`create_app`, a small factory that builds and
configures the FastAPI instance used by both the local development server
(`uvicorn`) and the AWS Lambda handler. Keeping the setup in a function makes
it easy for tests to create isolated apps and mirrors the pattern recommended
by FastAPI.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from backend.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
)
import backend.auth as auth

from backend.common.data_loader import resolve_paths
from backend.common.portfolio_utils import (
    _load_snapshot,
    refresh_snapshot_async,
    refresh_snapshot_in_memory,
)
from backend.config import reload_config
from backend import config_module

from backend.routes.agent import router as agent_router
from backend.routes.alert_settings import router as alert_settings_router
from backend.routes.alerts import router as alerts_router
from backend.routes.approvals import router as approvals_router
from backend.routes.compliance import router as compliance_router
from backend.routes.config import router as config_router
from backend.routes.goals import router as goals_router
from backend.routes.instrument import router as instrument_router
from backend.routes.instrument_admin import router as instrument_admin_router
from backend.routes.logs import router as logs_router
from backend.routes.metrics import router as metrics_router
from backend.routes.movers import router as movers_router
from backend.routes.models import router as models_router
from backend.routes.nudges import router as nudges_router
from backend.routes.news import router as news_router
from backend.routes.market import router as market_router
from backend.routes.pension import router as pension_router
from backend.routes.performance import router as performance_router
from backend.routes.portfolio import public_router as public_portfolio_router
from backend.routes.portfolio import router as portfolio_router
from backend.routes.query import router as query_router
from backend.routes.quotes import router as quotes_router
from backend.routes.events import router as events_router
from backend.routes.scenario import router as scenario_router
from backend.routes.screener import router as screener_router
from backend.routes.support import router as support_router
from backend.routes.tax import router as tax_router
from backend.routes.timeseries_admin import router as timeseries_admin_router
from backend.routes.timeseries_edit import router as timeseries_edit_router
from backend.routes.timeseries_meta import router as timeseries_router
from backend.routes.trading_agent import router as trading_agent_router
from backend.routes.transactions import router as transactions_router
from backend.routes.user_config import router as user_config_router
from backend.routes.virtual_portfolio import router as virtual_portfolio_router
from backend.routes.quest_routes import router as quest_router
from backend.routes.trail import router as trail_router
from backend.utils import page_cache

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    The function wires together middleware, registers routers and primes the
    in-memory price snapshot so the first request is quick. Returning the app
    instance instead of creating it at module import time keeps things
    test-friendly and avoids accidental state sharing between invocations.
    The configuration object is fetched lazily to ensure the latest values are
    used, even if other tests reload or replace it.
    """

    # Reload configuration but preserve any values that have been explicitly
    # overridden on the existing ``config`` object. Tests often monkeypatch
    # attributes like ``accounts_root`` or ``disable_auth`` before invoking
    # ``create_app`` and those should take precedence over values loaded from
    # disk or environment variables.
    prev_cfg = config_module.config
    overrides = {}
    if isinstance(prev_cfg, type(config_module.config)):
        for attr in (
            "accounts_root",
            "offline_mode",
            "disable_auth",
            "skip_snapshot_warm",
            "snapshot_warm_days",
            "app_env",
            "base_currency",
        ):
            overrides[attr] = getattr(prev_cfg, attr, None)

    cfg = reload_config()
    for attr, val in overrides.items():
        if val is not None:
            setattr(cfg, attr, val)

    if cfg.google_auth_enabled and not cfg.google_client_id:
        raise RuntimeError("google_client_id required when google_auth_enabled is true")

    # The FastAPI constructor accepts a few descriptive fields that end up in
    # the autogenerated OpenAPI/Swagger documentation. Startup and shutdown
    # logic is handled via a lifespan context manager to ensure all background
    # tasks are registered and later cleaned up.

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not cfg.skip_snapshot_warm:
            # Pre-fetch recent price data so the first request is fast.
            try:
                result = _load_snapshot()
                if not isinstance(result, tuple) or len(result) != 2 or not isinstance(result[0], dict):
                    raise ValueError("Malformed snapshot")
                snapshot, ts = result
            except Exception as exc:
                logger.error("Failed to load price snapshot: %s", exc)
                snapshot, ts = {}, None
            refresh_snapshot_in_memory(snapshot, ts)
            # Seed instrument API with the on-disk snapshot to avoid network
            # calls before the background refresh completes.
            from backend.common import instrument_api

            instrument_api.update_latest_prices_from_snapshot(snapshot)
            price_task = asyncio.create_task(asyncio.to_thread(instrument_api.prime_latest_prices))
            app.state.background_tasks.append(price_task)

        task = refresh_snapshot_async(days=cfg.snapshot_warm_days)
        if isinstance(task, (asyncio.Task, asyncio.Future)):
            app.state.background_tasks.append(task)
        yield
        # cancel any running background tasks
        tasks = list(app.state.background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await page_cache.cancel_refresh_tasks()
        for handler in logging.getLogger().handlers:
            try:
                handler.flush()
            except Exception:
                pass
        logging.shutdown()

    app = FastAPI(
        title="Allotmint API",
        version="1.0",
        docs_url="/docs",
        lifespan=lifespan,
    )
    app.state.background_tasks = []

    # ────────────────────────── CORS ──────────────────────────
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
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    paths = resolve_paths(cfg.repo_root, cfg.accounts_root)
    app.state.repo_root = paths.repo_root
    app.state.accounts_root = paths.accounts_root
    app.state.virtual_pf_root = paths.virtual_pf_root

    # ───────────────────────────── CORS ─────────────────────────────
    # The frontend origin varies by environment. Read the whitelist from
    # configuration and fall back to the production site plus the local
    # development servers if none are provided to avoid blocking dev requests.
    from urllib.parse import urlparse

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

    default_cors = [
        "https://app.allotmint.io",
        "http://localhost:3000",
        "http://localhost:5173",
    ]
    cors_origins = _validate_cors_origins(list(dict.fromkeys((cfg.cors_origins or []) + default_cors)))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    # Register SlowAPIMiddleware after CORSMiddleware so CORS preflight requests
    # are handled before rate limiting or other middleware runs.
    app.add_middleware(SlowAPIMiddleware)

    # ──────────────────────────── Routers ────────────────────────────
    # The API surface is composed of a few routers grouped by concern.
    # Sensitive routes are guarded by a JWT-based dependency.
    if cfg.disable_auth:
        protected = []
    else:
        protected = [Depends(auth.get_current_user)]
    # Public endpoints (e.g., demo access) are registered without authentication
    app.include_router(public_portfolio_router)
    app.include_router(portfolio_router, dependencies=protected)
    app.include_router(performance_router, dependencies=protected)
    app.include_router(instrument_router)
    # Administrative endpoints for editing instrument definitions. Authentication
    # is applied at include-time so `cfg.disable_auth` can skip it during
    # tests.
    app.include_router(instrument_admin_router, dependencies=protected)
    app.include_router(timeseries_router)
    app.include_router(timeseries_edit_router)
    app.include_router(timeseries_admin_router, dependencies=protected)
    app.include_router(transactions_router)
    app.include_router(alert_settings_router, dependencies=protected)
    app.include_router(alerts_router, dependencies=protected)
    app.include_router(nudges_router, dependencies=protected)
    app.include_router(quest_router, dependencies=protected)
    app.include_router(trail_router, dependencies=protected)
    app.include_router(compliance_router)
    app.include_router(screener_router)
    app.include_router(support_router)
    app.include_router(query_router, dependencies=protected)
    app.include_router(virtual_portfolio_router, dependencies=protected)
    app.include_router(metrics_router)
    app.include_router(agent_router)
    app.include_router(trading_agent_router, dependencies=protected)
    app.include_router(config_router)
    app.include_router(quotes_router)
    app.include_router(news_router)
    app.include_router(market_router)
    app.include_router(movers_router)
    app.include_router(models_router)
    app.include_router(user_config_router, dependencies=protected)
    app.include_router(approvals_router, dependencies=protected)
    app.include_router(events_router)
    app.include_router(scenario_router)
    app.include_router(logs_router)
    app.include_router(goals_router, dependencies=protected)
    app.include_router(tax_router)
    app.include_router(pension_router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Return 422 for body errors and 400 for query errors."""
        status = 422 if exc.body is not None else 400
        return JSONResponse(status_code=status, content={"detail": exc.errors()})

    class TokenIn(BaseModel):
        id_token: str

    @app.post("/token")
    async def login(body: TokenIn):
        try:
            email = auth.authenticate_user(body.id_token)
        except HTTPException as exc:
            logger.warning("User authentication failed: %s", exc.detail)
            raise

        if not email:
            logger.warning("authenticate_user returned no email")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = auth.create_access_token(email)
        return {"access_token": token, "token_type": "bearer"}

    @app.post("/token/google")
    async def google_token(payload: dict):
        token = payload.get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Missing token")
        try:
            email = auth.verify_google_token(token)
        except HTTPException as exc:
            logger.warning("Google token verification failed: %s", exc.detail)
            raise
        jwt_token = auth.create_access_token(email)
        return {"access_token": jwt_token, "token_type": "bearer"}

    # ────────────────────── Health-check endpoint ─────────────────────
    @app.get("/health")
    async def health():
        """Return a small payload used by tests and uptime monitors."""

        return {"status": "ok", "env": cfg.app_env}

    return app


# optional local test:  python -m backend.app
if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=reload_config().uvicorn_port or 8000,
    )
