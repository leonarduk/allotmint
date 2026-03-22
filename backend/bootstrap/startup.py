"""Application startup and shutdown services."""

from __future__ import annotations

import asyncio
import logging
import shutil
from importlib import import_module
from pathlib import Path

from fastapi import FastAPI
from backend.config import Config
from backend.utils import page_cache

logger = logging.getLogger(__name__)


def _snapshot_helpers():
    """Return snapshot helper callables, honoring backend.app compatibility aliases."""

    app_module = import_module("backend.app")
    portfolio_utils = import_module("backend.common.portfolio_utils")
    return (
        getattr(app_module, "_load_snapshot", portfolio_utils._load_snapshot),
        getattr(app_module, "refresh_snapshot_async", portfolio_utils.refresh_snapshot_async),
        getattr(app_module, "refresh_snapshot_in_memory", portfolio_utils.refresh_snapshot_in_memory),
    )


class AppLifecycleService:
    """Encapsulate startup warmup, background task registration, and shutdown cleanup."""

    def __init__(self, cfg: Config, temp_dirs: list[Path] | None = None):
        self.cfg = cfg
        self.temp_dirs = temp_dirs or []

    async def startup(self, app: FastAPI) -> None:
        if not self.cfg.skip_snapshot_warm:
            await self._warm_snapshot()

        _, refresh_snapshot_async, _ = _snapshot_helpers()
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
        load_snapshot, _, refresh_snapshot_in_memory = _snapshot_helpers()

        try:
            result = load_snapshot()
            if not isinstance(result, tuple) or len(result) != 2 or not isinstance(result[0], dict):
                raise ValueError("Malformed snapshot")
            snapshot, ts = result
        except Exception as exc:
            logger.error("Failed to load price snapshot: %s", exc)
            snapshot, ts = {}, None

        refresh_snapshot_in_memory(snapshot, ts)

        from backend.common import instrument_api

        instrument_api.update_latest_prices_from_snapshot(snapshot)
        try:
            await asyncio.to_thread(instrument_api.prime_latest_prices)
        except Exception:
            logger.exception("Failed to prime latest prices from warmed snapshot")
            raise

    @staticmethod
    def _flush_logging() -> None:
        for handler in logging.getLogger().handlers:
            try:
                handler.flush()
            except Exception:
                pass
        logging.shutdown()
