"""Helpers for caching route responses."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import BackgroundTasks

from . import page_cache


def cached_page(
    page: str,
    ttl: int,
    builder: Callable[[], Any],
    background_tasks: BackgroundTasks | None = None,
    language: str | None = None,
) -> Any:
    """Return cached JSON data for ``page`` or rebuild it.

    This wraps the common ``schedule_refresh``/``is_stale``/``load_cache``/
    ``save_cache`` sequence used by a number of endpoints. ``builder`` is a
    callable returning the data structure to serialize. The return value is
    either the cached payload or the freshly built result. ``language`` can be
    provided to maintain separate caches per localisation.
    """

    cache_key = f"{page}_{language}" if language else page

    # Ensure a background refresh task updates the cache periodically.
    page_cache.schedule_refresh(cache_key, ttl, builder)

    # Serve from cache when fresh data exists.
    if not page_cache.is_stale(cache_key, ttl):
        cached = page_cache.load_cache(cache_key)
        if cached is not None:
            return cached

    # Rebuild and persist the cache.
    data = builder()
    if background_tasks is None:
        page_cache.save_cache(cache_key, data)
    else:
        background_tasks.add_task(page_cache.save_cache, cache_key, data)
    return data
