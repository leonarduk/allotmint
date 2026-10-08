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
from backend.logging_setup import sanitise_log_value

CACHE_DIR = config.data_root / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_refresh_tasks: Dict[str, asyncio.Task] = {}

# Backoff after a failed refresh: 1s, 2s, 4s ... capped at the page's ttl
# (or _RETRY_MIN_SECONDS for a near-zero ttl, so a failure can never spin).
_RETRY_BASE_SECONDS = 1.0
_RETRY_MIN_SECONDS = 0.01

logger = logging.getLogger(__name__)


def _retry_delay(ttl: float, failures: int) -> float:
    """Return the wait before retry number ``failures`` (1-based) of a failed refresh."""

    cap = max(ttl, _RETRY_MIN_SECONDS)
    return min(cap, _RETRY_BASE_SECONDS * 2 ** min(failures - 1, 30))


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
        logger.exception("Cache load failed for %s", sanitise_log_value(page_name))
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


def cache_age(page_name: str) -> float | None:
    """Return the age in seconds of ``page_name``'s cache file, or ``None``."""

    path = _cache_path(page_name)
    if not path.exists():
        return None
    return time.time() - path.stat().st_mtime


def time_until_stale(page_name: str, ttl: int) -> float | None:
    """Return seconds until ``page_name`` becomes stale or ``None`` if missing."""

    path = _cache_path(page_name)
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    remaining = ttl - age
    if remaining <= 0:
        return 0.0
    return remaining


def schedule_refresh(
    page_name: str,
    ttl: int,
    builder: Callable[[], Any],
    can_refresh: Callable[[], bool] | None = None,
    *,
    initial_delay: float | None = None,
) -> None:
    """Ensure a background task keeps ``page_name`` cached every ``ttl`` seconds."""

    if page_name in _refresh_tasks:
        return

    if can_refresh is not None and not can_refresh():
        return

    # Callers running on a worker thread (e.g. via ``run_in_executor``, or a
    # sync FastAPI route) have no running event loop, so
    # ``asyncio.create_task`` would raise ``RuntimeError``. Skip the
    # background refresh rather than failing the caller. For such callers no
    # background refresh ever runs; they must keep the cache fresh on demand
    # by checking ``is_stale`` and rebuilding synchronously (as
    # ``get_cached_news`` does), and only a later call from the event loop
    # thread would schedule the refresh loop.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("No running event loop; skipping background refresh for %s", sanitise_log_value(page_name))
        return

    async def _call_builder() -> Any:
        if inspect.iscoroutinefunction(builder):
            return await builder()
        result = builder()
        if inspect.isawaitable(result):
            return await result
        return result

    async def _loop() -> None:
        try:
            if initial_delay is not None and initial_delay > 0:
                await asyncio.sleep(initial_delay)
            failures = 0
            # A built payload whose save failed, with when it was built. Only
            # the save is retried, so a persist error doesn't re-run an
            # expensive build on every attempt; once the payload is a ttl old
            # it is dropped and rebuilt rather than persisted stale.
            unsaved: tuple[float, Any] | None = None
            while True:
                if unsaved is not None and time.monotonic() - unsaved[0] > ttl:
                    unsaved = None
                if unsaved is None and can_refresh is not None and not can_refresh():
                    await asyncio.sleep(ttl)
                    continue
                stage = "refresh" if unsaved is None else "persist"
                try:
                    if unsaved is None:
                        unsaved = (time.monotonic(), await _call_builder())
                        stage = "persist"
                    save_cache(page_name, unsaved[1])
                except Exception:
                    # Retry sooner than the next scheduled refresh so a
                    # transient failure doesn't leave the cache cold for a
                    # whole ttl, but back off: retrying immediately turned a
                    # persistently failing build or save into a hot loop that
                    # pinned a core and logged a traceback per iteration
                    # (#10362).
                    failures += 1
                    delay = _retry_delay(ttl, failures)
                    logger.exception(
                        "Cache %s failed for %s (attempt %s); retrying in %ss",
                        sanitise_log_value(stage),
                        sanitise_log_value(page_name),
                        sanitise_log_value(failures),
                        sanitise_log_value(round(delay, 2)),
                    )
                    await asyncio.sleep(delay)
                    continue
                unsaved = None
                failures = 0
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
    except RuntimeError:  # pragma: no cover
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
