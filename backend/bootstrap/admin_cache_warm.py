"""Background warm-up of the admin pages' per-file caches (#10754).

GET /instrument/admin, /timeseries/admin and /data-quality/issues each scan
every instrument file or cached series. Their results are cached per file
(``list_instruments``, ``timeseries_admin``, ``aggregate_series_issues``), so
only the first scan after a restart is slow: on the full dataset (~12k
instrument files, ~1,000 series) that first scan took longer than the
frontend's 30s request timeout. Running it once at startup, off the event
loop, means the first page visit finds the caches already filled.

Only local deployments warm: on AWS/Lambda the caches are bypassed (S3 data)
and a frozen container would not keep a background thread running anyway.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable

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
    from backend.routes.timeseries_admin import timeseries_admin
    from backend.timeseries.cache import cache_only

    def series_issues() -> object:
        with cache_only():
            return aggregate_series_issues()

    return [
        ("instrument_list", list_instruments),
        ("timeseries_summaries", timeseries_admin),
        ("data_quality_series", series_issues),
    ]


def warm_admin_caches() -> dict[str, float]:
    """Fill the admin caches; return seconds taken per step. A failing step is logged and skipped."""
    timings: dict[str, float] = {}
    for name, step in _warm_steps():
        started = time.perf_counter()
        try:
            step()
        except Exception:
            logger.exception("Admin cache warm-up step %s failed", sanitise_log_value(name))
            continue
        timings[name] = round(time.perf_counter() - started, 2)
    logger.info("Admin page caches warmed: %s", sanitise_log_value(timings))
    return timings
