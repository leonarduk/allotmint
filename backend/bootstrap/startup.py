"""Application startup and shutdown services."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from fastapi import FastAPI

from backend.common.portfolio_utils import (
    _load_snapshot,
    refresh_snapshot_async,
    refresh_snapshot_in_memory,
)
from backend.config import Config
from backend.utils import page_cache

logger = logging.getLogger(__name__)


class AppLifecycleService:
    """Encapsulate startup warmup, background task registration, and shutdown cleanup."""

    def __init__(self, cfg: Config, temp_dirs: list[Path] | None = None):
        self.cfg = cfg
        self.temp_dirs = temp_dirs or []

    async def startup(self, app: FastAPI) -> None:
        if not self.cfg.skip_snapshot_warm:
            await self._warm_snapshot()

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

    async def _warm_snapshot(self) -> None:
        try:
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
            instrument_api.update_latest_prices_from_snapshot(snapshot)
        except Exception:
            logger.exception("Failed to update latest prices from snapshot")

        try:
            await asyncio.to_thread(instrument_api.prime_latest_prices)
        except Exception:
            # Non-fatal: price priming is a startup optimisation. If it fails (e.g.
            # network unavailable on Lambda cold start) the app should still serve
            # requests; a re-raise here propagates through the ASGI lifespan and
            # causes every subsequent request to return 500.
            logger.exception("Failed to prime latest prices from warmed snapshot")

    @staticmethod
    def _flush_logging() -> None:
        for handler in logging.getLogger().handlers:
            try:
                handler.flush()
            except Exception:
                pass
        logging.shutdown()
