"""Tests for request/thread-pool metrics and GET /health/runtime (#10359)."""

from __future__ import annotations

import asyncio
import logging
import threading

import anyio
import anyio.to_thread
import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from backend.common import request_metrics
from backend.common.request_metrics import RequestMetricsMiddleware, runtime_snapshot

LOGGER = "backend.common.request_metrics"


@pytest.fixture(autouse=True)
def fresh_metrics(monkeypatch):
    fresh = request_metrics._RequestMetrics()
    monkeypatch.setattr(request_metrics, "metrics", fresh)
    return fresh


def _app(*routes: Route) -> TestClient:
    app = Starlette(routes=list(routes))
    app.add_middleware(RequestMetricsMiddleware)
    return TestClient(app, raise_server_exceptions=False)


def _ok(_request):
    return PlainTextResponse("ok")


def _boom(_request):
    raise RuntimeError("boom")


def test_completed_request_is_counted_and_logged_at_info(fresh_metrics, caplog):
    client = _app(Route("/ok", _ok))
    with caplog.at_level(logging.INFO, logger=LOGGER):
        assert client.get("/ok").status_code == 200

    assert fresh_metrics.completed == 1
    assert fresh_metrics.in_flight == 0
    assert fresh_metrics.slow == fresh_metrics.cancelled == fresh_metrics.failed == 0
    record = next(r for r in caplog.records if r.event == "http.request_complete")
    assert record.levelno == logging.INFO
    assert record.path == "/ok"
    assert record.status == 200
    assert record.duration_ms >= 0
    assert record.skip_telegram is True
    # Readable in the plain-text console format too, which drops ``extra``.
    assert record.getMessage().startswith("http.request_complete GET /ok 200 ")
    assert record.getMessage().endswith("ms")


def test_slow_request_is_logged_at_warning_and_kept_in_recent(fresh_metrics, monkeypatch, caplog):
    monkeypatch.setattr(request_metrics, "SLOW_REQUEST_SECONDS", 0.0)
    client = _app(Route("/ok", _ok))
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        client.get("/ok")

    assert fresh_metrics.slow == 1
    assert fresh_metrics.recent_slow[0]["path"] == "/ok"
    slow_records = [r for r in caplog.records if r.event == "http.request_slow"]
    assert slow_records and slow_records[0].levelno == logging.WARNING


def test_recent_slow_is_bounded(fresh_metrics, monkeypatch):
    monkeypatch.setattr(request_metrics, "SLOW_REQUEST_SECONDS", 0.0)
    client = _app(Route("/ok", _ok))
    for _ in range(request_metrics._RECENT_SLOW_LIMIT + 5):
        client.get("/ok")

    assert len(fresh_metrics.recent_slow) == request_metrics._RECENT_SLOW_LIMIT


def test_app_exception_counts_as_failed_not_cancelled(fresh_metrics, caplog):
    client = _app(Route("/boom", _boom))
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert client.get("/boom").status_code == 500

    failed = next(r for r in caplog.records if r.event == "http.request_failed")
    assert failed.path == "/boom" and failed.duration_ms >= 0
    assert fresh_metrics.failed == 1
    assert fresh_metrics.cancelled == 0
    assert fresh_metrics.in_flight == 0


def test_cancelled_request_is_counted_and_logged(fresh_metrics, caplog):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise asyncio.CancelledError

    async def noop_send(_message):
        return None

    async def receive():
        return {"type": "http.disconnect"}

    scope = {"type": "http", "method": "GET", "path": "/slow-page"}
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(RequestMetricsMiddleware(app)(scope, receive, noop_send))

    assert fresh_metrics.cancelled == 1
    assert fresh_metrics.failed == 0
    assert fresh_metrics.in_flight == 0
    assert any(getattr(r, "event", None) == "http.request_cancelled" for r in caplog.records)


def test_in_flight_and_oldest_request_visible_during_request(fresh_metrics):
    seen = {}

    async def app(scope, receive, send):
        seen.update(runtime_snapshot()["requests"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def noop_send(_message):
        return None

    async def receive():
        return {"type": "http.request", "body": b""}

    scope = {"type": "http", "method": "GET", "path": "/portfolio/x"}
    asyncio.run(RequestMetricsMiddleware(app)(scope, receive, noop_send))

    assert seen["in_flight"] == 1
    assert seen["oldest_in_flight"]["path"] == "/portfolio/x"
    assert fresh_metrics.in_flight == 0


def test_snapshot_reports_busy_worker_threads():
    release = threading.Event()
    blockers = 3

    async def main():
        async with anyio.create_task_group() as tg:
            for _ in range(blockers):
                tg.start_soon(anyio.to_thread.run_sync, release.wait)
            await anyio.sleep(0.2)
            pool = runtime_snapshot()["threadpool"]
            release.set()
        return pool

    pool = anyio.run(main)
    assert pool["busy"] == blockers
    assert pool["total"] >= blockers
    assert pool["available"] == pool["total"] - blockers


def test_snapshot_outside_event_loop_has_no_threadpool():
    assert runtime_snapshot()["threadpool"] is None


def _scripted_receive(*messages):
    """Return an ASGI ``receive`` yielding ``messages`` in order, then disconnects."""

    queue = list(messages)

    async def receive():
        if queue:
            return queue.pop(0)
        await asyncio.sleep(0)
        return {"type": "http.disconnect"}

    return receive


async def _noop_send(_message):
    return None


def test_client_disconnect_while_handler_runs_is_logged_as_abandoned(fresh_metrics, caplog):
    seen_by_app = []

    async def app(scope, receive, send):
        # Stands in for a sync handler busy on a worker thread: it never
        # reads ``receive`` while it works.
        await asyncio.sleep(0.05)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"late"})
        seen_by_app.append(await receive())
        seen_by_app.append(await receive())

    scope = {"type": "http", "method": "GET", "path": "/portfolio/x", "headers": []}
    receive = _scripted_receive({"type": "http.request", "body": b""})
    with caplog.at_level(logging.INFO, logger=LOGGER):
        asyncio.run(RequestMetricsMiddleware(app)(scope, receive, _noop_send))

    assert fresh_metrics.abandoned == 1
    assert fresh_metrics.completed == 1 and fresh_metrics.cancelled == 0
    abandoned = next(r for r in caplog.records if r.event == "http.request_abandoned")
    assert abandoned.levelno == logging.WARNING and abandoned.path == "/portfolio/x"
    done = next(r for r in caplog.records if r.event == "http.request_complete")
    assert done.abandoned is True
    # Messages the watcher read are handed to the app, in order.
    assert [m["type"] for m in seen_by_app] == ["http.request", "http.disconnect"]


def test_request_body_is_passed_through_before_watching(fresh_metrics):
    bodies = []

    async def app(scope, receive, send):
        first = await receive()
        second = await receive()
        bodies.extend([first["body"], second["body"]])
        await asyncio.sleep(0.05)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    scope = {"type": "http", "method": "POST", "path": "/upload", "headers": []}
    receive = _scripted_receive(
        {"type": "http.request", "body": b"ab", "more_body": True},
        {"type": "http.request", "body": b"cd", "more_body": False},
    )
    asyncio.run(RequestMetricsMiddleware(app)(scope, receive, _noop_send))

    assert bodies == [b"ab", b"cd"]
    assert fresh_metrics.abandoned == 1


def test_normal_requests_are_not_abandoned(fresh_metrics):
    client = _app(Route("/ok", _ok), Route("/echo", _ok, methods=["POST"]))
    assert client.get("/ok").status_code == 200
    assert client.post("/echo", content=b"payload").status_code == 200

    assert fresh_metrics.abandoned == 0
    assert fresh_metrics.completed == 2


def test_disconnect_after_response_is_not_abandoned(fresh_metrics):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})
        await asyncio.sleep(0.01)

    scope = {"type": "http", "method": "GET", "path": "/ok", "headers": []}

    async def main():
        released = asyncio.Event()
        sent_request = False

        async def receive():
            nonlocal sent_request
            if not sent_request:
                sent_request = True
                return {"type": "http.request", "body": b""}
            await released.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body":
                released.set()

        await RequestMetricsMiddleware(app)(scope, receive, send)

    asyncio.run(main())
    assert fresh_metrics.abandoned == 0
    assert fresh_metrics.completed == 1


def test_health_runtime_endpoint_and_coarse_health(monkeypatch):
    from backend.app import create_app
    from backend.config import config

    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    with TestClient(create_app()) as client:
        health = client.get("/health").json()
        runtime = client.get("/health/runtime")

    assert set(health) == {"status", "env", "in_flight", "threadpool"}
    assert health["status"] == "ok"
    assert health["in_flight"] >= 1
    assert set(health["threadpool"]) == {"busy", "total"}
    assert runtime.status_code == 200
    body = runtime.json()
    assert body["status"] == "ok"
    assert body["threadpool"]["total"] > 0
    assert body["requests"]["in_flight"] >= 1
    assert "abandoned" in body["requests"]


def test_health_reports_degraded_when_pool_is_exhausted(monkeypatch):
    from backend.app import create_app
    from backend.config import config

    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", True)
    with TestClient(create_app()) as client:
        monkeypatch.setattr(request_metrics, "_thread_pool_usage", lambda: {"busy": 40, "total": 40, "available": 0})
        resp = client.get("/health")

    # Still HTTP 200: deploy probes and docker healthchecks only check the
    # status code, and the process is alive -- the body says it is saturated.
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["threadpool"] == {"busy": 40, "total": 40}
    assert "requests" not in body and "oldest_in_flight" not in body


def test_health_runtime_requires_admin_when_auth_enabled(monkeypatch):
    from backend.app import create_app
    from backend.config import config

    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    with TestClient(create_app()) as client:
        resp = client.get("/health/runtime")

    assert resp.status_code in {401, 403}
