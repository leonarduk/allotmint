"""Application startup and shutdown services."""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI

from backend.config import Config
from backend.utils import page_cache

logger = logging.getLogger(__name__)


@contextmanager
def _timed_phase(name: str):
    """Log how long a cold-start warmup phase took, in ``extra`` and in the message text.

    ``extra`` keeps the fields structured for whenever a JSON log formatter is in
    place; they're also inlined into the message so the timing is visible today
    with the plain text formatter.
    """
    start = time.monotonic()
    try:
        yield
    finally:
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        logger.info(
            "cold_start_phase phase=%s duration_ms=%s",
            name,
            duration_ms,
            extra={"phase": name, "duration_ms": duration_ms},
        )


class AppLifecycleService:
    """Encapsulate startup warmup, background task registration, and shutdown cleanup."""

    def __init__(self, cfg: Config, temp_dirs: list[Path] | None = None):
        self.cfg = cfg
        self.temp_dirs = temp_dirs or []

    async def startup(self, app: FastAPI) -> None:
        if not self.cfg.skip_snapshot_warm:
            await self._warm_snapshot(app)

        # Deferred import: portfolio_utils pulls in pandas; loading it here
        # (inside the lifespan startup hook) rather than at module level keeps
        # the Lambda INIT phase import chain lean.
        #
        # Pre-existing behaviour (not changed by this PR): refresh_snapshot_async
        # fires unconditionally — it is the background cache-refresh task that
        # keeps the snapshot up-to-date between warm-path invocations.  Only the
        # *blocking* _warm_snapshot() call is guarded by skip_snapshot_warm.
        from backend.common.portfolio_utils import refresh_snapshot_async

        task = refresh_snapshot_async(days=self.cfg.snapshot_warm_days)
        if isinstance(task, (asyncio.Task, asyncio.Future)):
            app.state.background_tasks.append(task)

    async def shutdown(self, app: FastAPI) -> None:
        tasks = list(getattr(app.state, "background_tasks", []))
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await page_cache.cancel_refresh_tasks()
        self._flush_logging()
        for temp_dir in self.temp_dirs:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _warm_snapshot(self, app: FastAPI) -> None:
        # Deferred imports: both pull in pandas transitively.
        from backend.common.portfolio_utils import (
            _load_snapshot,
            refresh_snapshot_in_memory,
        )

        try:
            with _timed_phase("snapshot_load"):
                result = _load_snapshot()
            if not isinstance(result, tuple) or len(result) != 2 or not isinstance(result[0], dict):
                raise ValueError("Malformed snapshot")
            snapshot, ts = result
        except Exception as exc:
            logger.error("Failed to load price snapshot: %s", exc)
            snapshot, ts = {}, None

        refresh_snapshot_in_memory(snapshot, ts)

        from backend.common import instrument_api

        try:
            with _timed_phase("metadata_update_from_snapshot"):
                instrument_api.update_latest_prices_from_snapshot(snapshot)
        except Exception:
            logger.exception("Failed to update latest prices from snapshot")

        # instrument_api.prime_latest_prices() can trigger a live Yahoo Finance
        # HTTP call per unknown/uncached ticker (price history and/or metadata
        # auto-create). On a Lambda cold start with many uncached tickers this
        # can take well over the function timeout. Run it as a background task
        # instead of awaiting it here, so lifespan startup (and therefore every
        # route, including /health) is never blocked on it.
        task = asyncio.create_task(self._prime_latest_prices_background())
        app.state.background_tasks.append(task)

    async def _prime_latest_prices_background(self) -> None:
        from backend.common import instrument_api

        try:
            with _timed_phase("price_history_fetch"):
                await asyncio.to_thread(instrument_api.prime_latest_prices)
        except Exception:
            # Non-fatal: price priming is a startup optimisation. If it fails (e.g.
            # network unavailable on Lambda cold start) the app should still serve
            # requests.
            logger.exception("Failed to prime latest prices from warmed snapshot")

    @staticmethod
    def _flush_logging() -> None:
        for handler in logging.getLogger().handlers:
            try:
                handler.flush()
            except Exception:
                pass
        logging.shutdown()
