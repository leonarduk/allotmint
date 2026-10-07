"""CORS headers on unhandled 500 responses (#9016).

Starlette's ServerErrorMiddleware sits outside CORSMiddleware, so without a
catch-all handler an unhandled exception produced a 500 with no CORS headers
and the browser reported an opaque network failure instead of the error.
"""

from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config

ORIGIN = "https://app.allotmint.io"


def _app(monkeypatch):
    monkeypatch.setattr(config, "cors_origins", [ORIGIN])
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()

    @app.get("/__boom")
    def boom():
        raise RuntimeError("boom")

    @app.get("/__teapot")
    def teapot():
        raise HTTPException(status_code=418, detail="short and stout")

    return app


def test_unhandled_500_carries_cors_headers(monkeypatch):
    app = _app(monkeypatch)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/__boom", headers={"Origin": ORIGIN})
    assert resp.status_code == 500
    assert resp.text == "Internal Server Error"
    assert resp.headers["access-control-allow-origin"] == ORIGIN
    assert resp.headers["access-control-allow-credentials"] == "true"


def test_unhandled_500_before_cors_middleware_carries_cors_headers(monkeypatch):
    """A failure in middleware outside CORSMiddleware is still covered.

    ``@app.middleware`` inserts the middleware outermost, and it raises without
    calling ``call_next``, so CORSMiddleware never runs: the headers can only
    come from the catch-all handler.
    """
    app = _app(monkeypatch)

    @app.middleware("http")
    async def explode(request: Request, call_next):
        raise RuntimeError("early boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/health", headers={"Origin": ORIGIN})
    assert resp.status_code == 500
    assert resp.text == "Internal Server Error"
    assert resp.headers["access-control-allow-origin"] == ORIGIN


def test_unhandled_500_does_not_allow_unlisted_origin(monkeypatch):
    app = _app(monkeypatch)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/__boom", headers={"Origin": "https://evil.com"})
    assert resp.status_code == 500
    assert "access-control-allow-origin" not in resp.headers


def test_unhandled_500_without_origin_is_unchanged(monkeypatch):
    app = _app(monkeypatch)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/__boom")
    assert resp.status_code == 500
    assert resp.text == "Internal Server Error"
    assert "access-control-allow-origin" not in resp.headers


def test_handled_http_exception_is_unaffected(monkeypatch):
    """Specific handlers still win over the catch-all ``Exception`` handler."""
    app = _app(monkeypatch)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/__teapot", headers={"Origin": ORIGIN})
    assert resp.status_code == 418
    assert resp.json() == {"detail": "short and stout"}
    assert resp.headers["access-control-allow-origin"] == ORIGIN
