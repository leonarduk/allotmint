"""Simple JSON file cache for expensive page responses.

Cache files live under ``data/cache/<page_name>.json`` and store the raw
JSON-serialised payload returned by the API. Helpers below provide small
wrappers to load/save the cache and determine whether it has expired.

A lightweight scheduler keeps cached pages fresh by calling the original
builder function at a fixed interval.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict

from backend.config import config

CACHE_DIR = config.data_root / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_refresh_tasks: Dict[str, asyncio.Task] = {}

logger = logging.getLogger(__name__)


def _cache_path(page_name: str) -> Path:
    return CACHE_DIR / f"{page_name}.json"


def load_cache(page_name: str) -> Any | None:
    """Return cached JSON data for ``page_name`` or ``None`` if missing."""

    path = _cache_path(page_name)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        logger.exception("Cache load failed for %s", page_name)
        return None


def save_cache(page_name: str, data: Any) -> None:
    """Persist ``data`` under the cache file for ``page_name``."""

    path = _cache_path(page_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, default=str)


def is_stale(page_name: str, ttl: int) -> bool:
    """Return ``True`` if the cache file is older than ``ttl`` seconds."""

    path = _cache_path(page_name)
    if not path.exists():
        return True
    age = time.time() - path.stat().st_mtime
    return age > ttl


def schedule_refresh(page_name: str, ttl: int, builder: Callable[[], Any]) -> None:
    """Ensure a background task keeps ``page_name`` cached every ``ttl`` seconds."""

    if page_name in _refresh_tasks:
        return

    async def _call_builder() -> Any:
        if inspect.iscoroutinefunction(builder):
            return await builder()
        result = await asyncio.to_thread(builder)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _loop() -> None:
        try:
            while True:
                try:
                    data = await _call_builder()
                except Exception as exc:
                    if isinstance(exc, asyncio.CancelledError):  # pragma: no cover - defensive
                        raise
                    logger.exception("Cache refresh failed for %s", page_name)
                    # Immediately retry on failure so the cache can still be
                    # populated without waiting for the next scheduled
                    # interval.  This makes the refresh logic resilient to
                    # short "ttl" values and slower platforms where the
                    # first attempt may take longer than expected (for
                    # example on Windows CI where thread start-up can be
                    # noticeably slower).  By continuing here we skip the
                    # sleep below and run the builder again right away.
                    continue

                cancelled = False
                while True:
                    try:
                        save_cache(page_name, data)
                        break
                    except BaseException as exc:
                        if isinstance(exc, asyncio.CancelledError):
                            cancelled = True
                        else:
                            logger.exception("Cache persist failed for %s", page_name)
                        try:
                            await asyncio.sleep(0)
                        except asyncio.CancelledError:
                            cancelled = True

                if cancelled:
                    raise asyncio.CancelledError

                await asyncio.sleep(ttl)
        except asyncio.CancelledError:  # pragma: no cover - defensive
            pass

    _refresh_tasks[page_name] = asyncio.create_task(_loop())


async def cancel_refresh_tasks() -> None:
    """Cancel all scheduled refresh tasks and wait for them to finish."""

    tasks = list(_refresh_tasks.values())
    current_loop = None
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        pass

    for task in tasks:
        task.cancel()
    for task in tasks:
        loop = task.get_loop()
        if current_loop is not None and loop is current_loop and not loop.is_closed():
            try:
                await task
            except Exception:
                pass
    _refresh_tasks.clear()
