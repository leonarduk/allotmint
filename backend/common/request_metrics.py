"""In-process request metrics: latency, in-flight count and thread-pool use (#10359).

Sync route handlers run on AnyIO's default worker pool (40 threads). When
slow requests fill it, every other sync route queues while ``/health`` -- an
async route that never touches the pool -- still answers instantly. This
module records what is needed to see that state: :func:`health_summary` gives
``/health`` coarse counters and a ``degraded`` status, and
:func:`runtime_snapshot` gives the admin-only ``/health/runtime`` the detail
(paths of the oldest and recent slow requests).

Logging: every completed request is logged at INFO as ``http.request_complete``
with method, path, status and ``duration_ms`` (uvicorn's access log has no
durations). Requests slower than :data:`SLOW_REQUEST_SECONDS` are logged at
WARNING as ``http.request_slow`` instead, and requests whose client
disconnected before the response finished as ``http.request_abandoned``.
These diagnostic warnings carry ``skip_telegram`` so a slow page does not
page anyone.

Abandoned requests: a sync handler never reads the ASGI ``receive`` channel,
and uvicorn only notices a closed socket while something is waiting on
``receive``. So once the app has consumed the request body, the middleware
keeps one ``receive`` call pending in a watcher task; if it returns
``http.disconnect`` before the response is complete, the client gave up.
Messages the watcher reads are handed to the app on its own next ``receive``
call, so nothing is lost and the request body is never read ahead. (A request
with a body that the app never reads is not watched.)

All counters are updated on the event-loop thread, so they need no lock.
"""

from __future__ import annotations

import asyncio
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
_BODYLESS_METHODS = frozenset({"GET", "HEAD", "DELETE", "OPTIONS"})
_DISCONNECT: Message = {"type": "http.disconnect"}


@dataclass
class _RequestMetrics:
    in_flight: int = 0
    completed: int = 0
    slow: int = 0
    cancelled: int = 0
    failed: int = 0
    abandoned: int = 0
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


def health_summary() -> Dict[str, Any]:
    """Return the coarse, unauthenticated-safe saturation view for ``GET /health``.

    Only integer counters and a status -- no paths, owners or timings -- so
    it is safe on the public probe. ``status`` is ``"degraded"`` when every
    worker thread is busy, i.e. any new sync request would queue.
    """

    pool = _thread_pool_usage()
    degraded = pool is not None and pool["available"] <= 0
    summary: Dict[str, Any] = {
        "status": "degraded" if degraded else "ok",
        "in_flight": metrics.in_flight,
    }
    if pool is not None:
        summary["threadpool"] = {"busy": pool["busy"], "total": pool["total"]}
    return summary


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
            "abandoned": metrics.abandoned,
            "slow_threshold_ms": SLOW_REQUEST_SECONDS * 1000,
            "recent_slow": list(metrics.recent_slow),
        },
    }


class _DisconnectWatcher:
    """Wrap ``receive`` so a client disconnect is seen while the app is busy.

    Until the request body is fully read, ``receive`` is passed straight
    through. After that, a watcher task keeps one ``receive`` call pending;
    whatever it gets is queued for the app's next ``receive`` call, and an
    ``http.disconnect`` before the response completes marks the request
    abandoned.
    """

    def __init__(self, receive: Receive, state: Dict[str, Any], on_abandoned: Any) -> None:
        self._receive = receive
        self._state = state
        self._on_abandoned = on_abandoned
        self._queue: asyncio.Queue[Message] = asyncio.Queue()
        self._task: Optional[asyncio.Task[None]] = None
        self._disconnected = False

    def start(self, body_read: bool = True) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._watch(body_read))

    async def _watch(self, body_read: bool) -> None:
        while True:
            message = await self._receive()
            if message["type"] == "http.disconnect":
                self._disconnected = True
                if not self._state["complete"]:
                    self._on_abandoned()
            elif body_read:
                # Only a disconnect can follow the final body message; anything
                # else is a server that does not behave like uvicorn, so hand
                # it over and stop watching rather than spin.
                self._queue.put_nowait(message)
                return
            else:
                body_read = not message.get("more_body", False)
            self._queue.put_nowait(message)
            if self._disconnected:
                return

    async def receive(self) -> Message:
        if self._task is None:
            message = await self._receive()
            if message["type"] == "http.request" and not message.get("more_body", False):
                self.start()
            return message
        if self._disconnected and self._queue.empty():
            return _DISCONNECT
        return await self._queue.get()

    async def stop(self) -> None:
        if self._task is None or self._task.done():
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass


def _has_body(scope: Scope) -> bool:
    if str(scope.get("method", "")).upper() not in _BODYLESS_METHODS:
        return True
    for name, value in scope.get("headers") or ():
        if name == b"transfer-encoding" or (name == b"content-length" and value.strip() not in (b"", b"0")):
            return True
    return False


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
        state: Dict[str, Any] = {"status": 0, "complete": False, "abandoned": False}

        def on_abandoned() -> None:
            state["abandoned"] = True
            _record_abandoned(method, path, started)

        watcher = _DisconnectWatcher(receive, state, on_abandoned)
        if not _has_body(scope):
            # No body for the app to read: watch for a disconnect straight away.
            watcher.start(body_read=False)

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
            await self.app(scope, watcher.receive, send_wrapper)
        except Exception:
            # Starlette's ServerErrorMiddleware, which sits outside this one,
            # logs the traceback and turns it into a 500. A cancelled request
            # task raises a BaseException instead and is counted as cancelled.
            failed = True
            raise
        finally:
            await watcher.stop()
            metrics.in_flight -= 1
            metrics.started_at.pop(request_id, None)
            _record_completion(method, path, state, failed, started)


def _log_fields(method: str, path: str, status: int, started: float) -> Dict[str, Any]:
    return {
        "method": sanitise_log_value(method),
        "path": sanitise_log_value(path),
        "status": status,
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        "in_flight": metrics.in_flight,
    }


def _log(level: int, event: str, fields: Dict[str, Any]) -> None:
    # Key fields go in the message too, so the plain-text console format
    # (which drops ``extra``) still shows them; backend.log's JSON keeps them
    # as separate keys.
    logger.log(
        level,
        "%s %s %s %s %.1fms",
        event,
        fields["method"],
        fields["path"],
        fields["status"],
        fields["duration_ms"],
        extra={"event": event, "skip_telegram": True, **fields},
    )


def _record_abandoned(method: str, path: str, started: float) -> None:
    metrics.abandoned += 1
    _log(logging.WARNING, "http.request_abandoned", _log_fields(method, path, 0, started))


def _record_completion(method: str, path: str, state: Dict[str, Any], failed: bool, started: float) -> None:
    fields = _log_fields(method, path, int(state["status"]), started)
    metrics.completed += 1
    if failed:
        metrics.failed += 1
        _log(logging.WARNING, "http.request_failed", {**fields, "status": 500})
        return

    if state["abandoned"]:
        # Already logged when the disconnect was seen; this line records how
        # long the work carried on with nobody waiting for it.
        fields["abandoned"] = True

    if not state["complete"]:
        # The request task was cancelled before its response finished (e.g.
        # server shutdown or reload). A sync handler's worker thread cannot
        # be cancelled, so its work may still be running.
        metrics.cancelled += 1
        _log(logging.WARNING, "http.request_cancelled", fields)
        return

    if fields["duration_ms"] >= SLOW_REQUEST_SECONDS * 1000:
        metrics.slow += 1
        metrics.recent_slow.append({k: fields[k] for k in ("method", "path", "status", "duration_ms")})
        del metrics.recent_slow[:-_RECENT_SLOW_LIMIT]
        _log(logging.WARNING, "http.request_slow", fields)
        return

    _log(logging.INFO, "http.request_complete", fields)


__all__ = [
    "RequestMetricsMiddleware",
    "SLOW_REQUEST_SECONDS",
    "health_summary",
    "metrics",
    "runtime_snapshot",
]
