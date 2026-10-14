"""Background warm-up of the admin pages' per-file caches (#10754).

GET /instrument/admin, /timeseries/admin and /data-quality/issues each scan
every instrument file or cached series. Their results are cached per file
(``list_instruments``, ``timeseries_admin``, ``aggregate_series_issues``), so
only the first scan after a restart is slow: on the full dataset (~12k
instrument files, ~1,000 series) that first scan took longer than the
frontend's 30s request timeout. Running it once at startup, on a daemon
thread off the event loop, means the first page visit finds the caches
already filled, and stopping or reloading the server never waits for it.

While a step is still running, the matching endpoint can serve what is
already cached instead of blocking on its own cold scan: the admin pages ask
for that with ``?partial=true`` and get the warming header back until the
step finishes (see :mod:`backend.common.admin_cache_state`), so a visit
straight after a restart shows rows at once and fills in as the warm-up
progresses.

Only local deployments warm: on AWS/Lambda the caches are bypassed (S3 data)
and a frozen container would not keep a background thread running anyway.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable

from backend.common.admin_cache_state import (
    DATA_QUALITY_SERIES,
    INSTRUMENT_LIST,
    TIMESERIES_SUMMARIES,
    WARM_STEP_NAMES,
    finish_all_steps,
    finish_step,
    mark_steps_pending,
)
from backend.config import Config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)


def should_warm_admin_caches(cfg: Config) -> bool:
    """True for a local, non-test server."""
    if os.getenv("TESTING") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        return False
    return cfg.app_env != "aws"


def _warm_steps() -> list[tuple[str, Callable[[], object]]]:
    # Deferred imports: each pulls in pandas and the route modules.
    from backend.common.instruments import list_instruments
    from backend.data_quality.issues import aggregate_series_issues
    from backend.routes.timeseries_admin import local_timeseries_summaries
    from backend.timeseries.cache import cache_only

    def series_issues() -> object:
        with cache_only():
            return aggregate_series_issues()

    return [
        (INSTRUMENT_LIST, list_instruments),
        (TIMESERIES_SUMMARIES, local_timeseries_summaries),
        (DATA_QUALITY_SERIES, series_issues),
    ]


def warm_admin_caches() -> dict[str, float]:
    """Fill the admin caches; return seconds taken per step. A failing step is logged and skipped."""
    timings: dict[str, float] = {}
    try:
        for name, step in _warm_steps():
            started = time.perf_counter()
            try:
                step()
            except Exception:
                logger.exception("Admin cache warm-up step %s failed", sanitise_log_value(name))
                continue
            finally:
                # A failed step stops serving partial results too: its endpoint
                # falls back to scanning on request, as it would without warm-up.
                finish_step(name)
            timings[name] = round(time.perf_counter() - started, 2)
    finally:
        finish_all_steps()
    logger.info("Admin page caches warmed: %s", sanitise_log_value(timings))
    return timings


def _warm_in_background() -> None:
    try:
        warm_admin_caches()
    except Exception:
        # Non-fatal: the caches fill on the first request instead.
        logger.exception("Failed to warm admin page caches")


def start_admin_cache_warm_thread() -> threading.Thread:
    """Start :func:`warm_admin_caches` on a daemon thread and return it.

    Not ``asyncio.to_thread``: the event loop's default executor is joined at
    shutdown, so Ctrl+C or a ``--reload`` mid-scan would hang until the scan
    finished. A daemon thread is simply abandoned.
    """
    mark_steps_pending(WARM_STEP_NAMES)
    thread = threading.Thread(target=_warm_in_background, name="admin-cache-warm", daemon=True)
    try:
        thread.start()
    except BaseException:
        finish_all_steps()
        raise
    return thread
