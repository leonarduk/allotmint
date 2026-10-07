"""In-process request metrics: latency, in-flight count and thread-pool use (#10359).

Sync route handlers run on AnyIO's default worker pool (40 threads). When
slow requests fill it, every other sync route queues while ``/health`` -- an
async route that never touches the pool -- still answers instantly, so the
app looks healthy while being unusable. :class:`RequestMetricsMiddleware`
records what is needed to see that state, and :func:`runtime_snapshot` reports
it for ``GET /health/runtime``.

Logging is deliberately sparse: uvicorn's access log already records every
request, so each completed request is logged at DEBUG only. Requests slower
than :data:`SLOW_REQUEST_SECONDS`, and cancelled requests, are logged at
WARNING.

What this cannot see: a client that gave up (browser timeout, navigation)
while a *sync* route was running. Nothing in the stack reads the ASGI
``receive`` channel during a sync handler, and uvicorn silently drops writes
to a closed connection, so such a request looks completed here. Its duration
-- usually past the frontend's timeout -- is what gives it away in the slow
log, and ``oldest_in_flight`` shows it while it is still running.

All counters are updated on the event-loop thread, so they need no lock.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import anyio.to_thread
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

SLOW_REQUEST_SECONDS = 5.0
_RECENT_SLOW_LIMIT = 10


@dataclass
class _RequestMetrics:
    in_flight: int = 0
    completed: int = 0
    slow: int = 0
    cancelled: int = 0
    failed: int = 0
    started_at: Dict[int, tuple[str, str, float]] = field(default_factory=dict)
    recent_slow: List[Dict[str, Any]] = field(default_factory=list)


metrics = _RequestMetrics()


def _thread_pool_usage() -> Optional[Dict[str, int]]:
    """Return AnyIO default thread-limiter usage, or ``None`` outside an event loop."""

    try:
        limiter = anyio.to_thread.current_default_thread_limiter()
    except RuntimeError:
        return None
    total = int(limiter.total_tokens)
    busy = int(limiter.borrowed_tokens)
    return {"busy": busy, "total": total, "available": total - busy}


def runtime_snapshot() -> Dict[str, Any]:
    """Return current request and thread-pool metrics; call from the event loop."""

    now = time.perf_counter()
    oldest: Optional[Dict[str, Any]] = None
    if metrics.started_at:
        method, path, started = min(metrics.started_at.values(), key=lambda entry: entry[2])
        oldest = {"method": method, "path": path, "age_ms": round((now - started) * 1000, 1)}
    return {
        "threadpool": _thread_pool_usage(),
        "requests": {
            "in_flight": metrics.in_flight,
            "oldest_in_flight": oldest,
            "completed": metrics.completed,
            "failed": metrics.failed,
            "slow": metrics.slow,
            "cancelled": metrics.cancelled,
            "slow_threshold_ms": SLOW_REQUEST_SECONDS * 1000,
            "recent_slow": list(metrics.recent_slow),
        },
    }


class RequestMetricsMiddleware:
    """Pure-ASGI middleware timing every HTTP request.

    Pure ASGI rather than ``BaseHTTPMiddleware`` so it adds no task layer and
    passes streaming responses through untouched. Register it outermost so it
    times the whole stack, including the other middleware.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", ""))
        path = str(scope.get("path", ""))
        started = time.perf_counter()
        request_id = id(scope)
        state = {"status": 0, "complete": False}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                state["status"] = int(message["status"])
            elif message["type"] == "http.response.body" and not message.get("more_body", False):
                state["complete"] = True
            await send(message)

        metrics.in_flight += 1
        metrics.started_at[request_id] = (method, path, started)
        failed = False
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # Logged (with traceback) and turned into a 500 by Starlette's
            # ServerErrorMiddleware, which sits outside this one. A cancelled
            # request task raises a BaseException instead and is counted as
            # cancelled below.
            failed = True
            raise
        finally:
            metrics.in_flight -= 1
            metrics.started_at.pop(request_id, None)
            _record_completion(method, path, int(state["status"]), bool(state["complete"]), failed, started)


def _record_completion(method: str, path: str, status: int, complete: bool, failed: bool, started: float) -> None:
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    metrics.completed += 1
    if failed:
        metrics.failed += 1
        return
    fields = {
        "method": sanitise_log_value(method),
        "path": sanitise_log_value(path),
        "status": status,
        "duration_ms": duration_ms,
        "in_flight": metrics.in_flight,
    }

    if not complete:
        # The request task was cancelled before its response finished (e.g.
        # server shutdown or reload). A sync handler's worker thread cannot
        # be cancelled, so its work may still be running.
        metrics.cancelled += 1
        logger.warning("http.request_cancelled", extra={"event": "http.request_cancelled", **fields})
        return

    if duration_ms >= SLOW_REQUEST_SECONDS * 1000:
        metrics.slow += 1
        metrics.recent_slow.append({k: fields[k] for k in ("method", "path", "status", "duration_ms")})
        del metrics.recent_slow[:-_RECENT_SLOW_LIMIT]
        logger.warning("http.request_slow", extra={"event": "http.request_slow", **fields})
        return

    logger.debug("http.request_complete", extra={"event": "http.request_complete", **fields})


__all__ = ["RequestMetricsMiddleware", "SLOW_REQUEST_SECONDS", "metrics", "runtime_snapshot"]
