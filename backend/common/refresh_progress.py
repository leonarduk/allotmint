"""In-memory progress tracker for the "refresh prices" job.

Single-slot state: only one manual price refresh is expected to run at a
time (triggered from the Support page). A concurrent second refresh
overwrites the same slot — an accepted tradeoff for a status-only signal
with no correctness implications for pricing itself.

Reporting is opt-in, not merely gated on ``running``: only the exact call
chain started by ``prices.refresh_prices`` (via its
``_reporting_progress()`` context, read by ``get_price_snapshot`` and
forwarded to ``holding_utils.load_latest_prices(report_progress=True)``)
ever calls ``update``. Other callers of ``load_latest_prices`` (e.g.
building ``instrument_api``'s in-memory price map) default to
``report_progress=False`` and pass an unrelated, differently-sized ticker
list, so they can never overwrite the refresh job's progress with their own
counts — even if they happen to run concurrently with a tracked refresh.

Known limitation: on Lambda, this state lives in one container's memory.
``POST /prices/refresh`` and a later ``GET /prices/refresh/progress`` poll
are separate invocations and can land on different warm instances; when
they do, the poll sees the idle default (``running: False``) even though a
refresh is genuinely in progress elsewhere. This degrades to the pre-this-
feature behaviour (a static "Refreshing..." label) rather than to anything
incorrect or worse, but it does mean the progress bar isn't guaranteed to
appear on every refresh in that deployment topology. Making it reliable
there would need a shared store (e.g. a DynamoDB/S3-backed progress key) or
sticky routing between the two calls; deliberately not built, since this
is a best-effort status signal for a Low Value UX issue (#8015), not a
distributed job-tracking system. Instead (#8055) the Support page counts
polls that return no progress and, after a few, says explicitly that the
refresh is running but detailed progress is unavailable.
"""

from __future__ import annotations

import threading
from typing import Optional, TypedDict


class RefreshProgress(TypedDict):
    running: bool
    total: int
    completed: int
    current_ticker: Optional[str]


_lock = threading.Lock()
_state: RefreshProgress = {
    "running": False,
    "total": 0,
    "completed": 0,
    "current_ticker": None,
}


def start(total: int) -> None:
    with _lock:
        _state["running"] = True
        _state["total"] = total
        _state["completed"] = 0
        _state["current_ticker"] = None


def update(current_ticker: str, completed: int) -> None:
    """Record progress after processing one ticker.

    ``completed`` counts tickers *attempted*, not tickers priced
    successfully — callers advance it whether or not that ticker's fetch
    succeeded, so the bar reliably reaches ``total`` rather than stalling on
    a skipped/errored ticker.
    """
    with _lock:
        if not _state["running"]:
            return
        _state["current_ticker"] = current_ticker
        _state["completed"] = completed


def finish() -> None:
    with _lock:
        _state["running"] = False
        _state["current_ticker"] = None


def snapshot() -> RefreshProgress:
    with _lock:
        return dict(_state)  # type: ignore[return-value]
