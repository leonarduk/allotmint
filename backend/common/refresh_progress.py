"""In-memory progress tracker for the "refresh prices" job.

Single-slot state: only one manual price refresh is expected to run at a
time (triggered from the Support page). A concurrent second refresh
overwrites the same slot, and unrelated callers of ``load_latest_prices``
outside a tracked refresh are ignored (``update`` no-ops while nothing is
``running``). That is an accepted tradeoff for a status-only signal with no
correctness implications for pricing itself.
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
