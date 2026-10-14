"""Which admin-cache warm-up steps are still running (#10754).

Kept apart from :mod:`backend.bootstrap.admin_cache_warm` so the route
modules can read it without importing the bootstrap package, which imports
them.

While a step is pending, its endpoint can answer ``?partial=true`` from
whatever is already cached instead of blocking on its own cold scan, and sets
:data:`WARMING_HEADER` so the page knows the list is incomplete.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable

INSTRUMENT_LIST = "instrument_list"
TIMESERIES_SUMMARIES = "timeseries_summaries"
DATA_QUALITY_SERIES = "data_quality_series"
WARM_STEP_NAMES = (INSTRUMENT_LIST, TIMESERIES_SUMMARIES, DATA_QUALITY_SERIES)

# Set on a response that is a partial, cache-only result.
WARMING_HEADER = "X-Admin-Cache-Warming"

_pending_steps: set[str] = set()
_pending_lock = threading.Lock()


def is_step_warming(name: str) -> bool:
    """True while warm-up step ``name`` is scheduled or running."""
    with _pending_lock:
        return name in _pending_steps


def mark_steps_pending(names: Iterable[str]) -> None:
    with _pending_lock:
        _pending_steps.update(names)


def finish_step(name: str) -> None:
    with _pending_lock:
        _pending_steps.discard(name)


def finish_all_steps() -> None:
    with _pending_lock:
        _pending_steps.clear()
