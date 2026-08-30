"""Integration tests for the global demo write-blocking gate (#7407).

Exercises ``backend.bootstrap.middleware.register_middleware``'s
``demo_write_gate`` HTTP middleware: a demo-scoped token (see
``backend.auth.create_demo_access_token`` / ``decode_demo_token``, #7405) must
never reach a mutating handler, on *any* router, regardless of whether that
router carries a router-level ``Depends(auth.get_current_user)`` (#7406's
identity resolution is a separate concern -- these tests only assert on the
method-based gate itself).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from backend import auth
from backend.app import create_app
from backend.bootstrap.middleware import register_middleware
from backend.config import Config

DEMO_BLOCKED_DETAIL = "Demo access is read-only"


@pytest.fixture(scope="module")
def demo_token() -> str:
    return auth.create_demo_access_token("demo")


@pytest.fixture(scope="module")
def real_token() -> str:
    return auth.create_access_token("real@example.com")


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("TESTING", "1")
    app = create_app()
    return TestClient(app)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Demo-scoped token: non-safe methods are rejected everywhere -----------


def test_post_transactions_with_demo_token_is_rejected(client: TestClient, demo_token: str) -> None:
    """``transactions_router`` carries no router-level auth dependency at all
    (backend/bootstrap/routers.py) -- the sharpest case for proving this gate
    is genuinely global rather than per-route."""

    response = client.post("/transactions", json={}, headers=_bearer(demo_token))

    assert response.status_code == 403
    assert response.json()["detail"] == DEMO_BLOCKED_DETAIL


def test_post_holdings_manual_with_demo_token_is_rejected(client: TestClient, demo_token: str) -> None:
    response = client.post("/holdings/manual", json={}, headers=_bearer(demo_token))

    assert response.status_code == 403
    assert response.json()["detail"] == DEMO_BLOCKED_DETAIL


def test_delete_transactions_with_demo_token_is_rejected(client: TestClient, demo_token: str) -> None:
    response = client.delete("/transactions/demo-acc-0", headers=_bearer(demo_token))

    assert response.status_code == 403
    assert response.json()["detail"] == DEMO_BLOCKED_DETAIL


def test_patch_with_demo_token_is_rejected(client: TestClient, demo_token: str) -> None:
    """The gate runs as middleware, ahead of routing -- it rejects a non-safe
    method for a demo token even against a path with no PATCH route at all,
    proving the check does not depend on a route existing/opting in."""

    response = client.patch("/transactions/demo-acc-0", headers=_bearer(demo_token))

    assert response.status_code == 403
    assert response.json()["detail"] == DEMO_BLOCKED_DETAIL


def test_put_with_demo_token_is_rejected(client: TestClient, demo_token: str) -> None:
    response = client.put("/transactions/demo-acc-0", json={}, headers=_bearer(demo_token))

    assert response.status_code == 403
    assert response.json()["detail"] == DEMO_BLOCKED_DETAIL


# --- Safe methods and demo tokens are unaffected ----------------------------


def test_get_with_demo_token_is_not_blocked_by_this_gate(client: TestClient, demo_token: str) -> None:
    """A GET is never rejected by this gate. The route below does not exist,
    so a 404 (routing, not this middleware) is expected -- the point is that
    it is not this gate's 403/detail."""

    response = client.get("/definitely-not-a-real-route", headers=_bearer(demo_token))

    assert response.status_code != 403
    assert response.status_code == 404


def test_options_preflight_with_demo_token_is_not_blocked(client: TestClient, demo_token: str) -> None:
    response = client.options(
        "/transactions",
        headers={
            **_bearer(demo_token),
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code != 403


# --- Non-demo requests are unaffected ---------------------------------------


def test_post_transactions_with_real_token_is_unaffected(client: TestClient, real_token: str) -> None:
    """No regression: a real user's POST is never rejected by this gate (it
    may still fail for unrelated reasons -- validation, missing store, etc.
    -- but never with this gate's 403 detail)."""

    response = client.post("/transactions", json={}, headers=_bearer(real_token))

    assert not (response.status_code == 403 and response.json().get("detail") == DEMO_BLOCKED_DETAIL)


def test_post_transactions_with_no_token_is_unaffected(client: TestClient) -> None:
    response = client.post("/transactions", json={})

    assert not (response.status_code == 403 and response.json().get("detail") == DEMO_BLOCKED_DETAIL)


# --- disable_auth does not unlock writes for a demo token -------------------


def test_disable_auth_does_not_exempt_demo_token_from_gate(monkeypatch: pytest.MonkeyPatch, demo_token: str) -> None:
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("DISABLE_AUTH", "true")
    app = create_app()
    assert app.state.limiter is not None  # sanity: app actually built

    with TestClient(app) as disable_auth_client:
        response = disable_auth_client.post("/transactions", json={}, headers=_bearer(demo_token))

    assert response.status_code == 403
    assert response.json()["detail"] == DEMO_BLOCKED_DETAIL


# --- Full safelist coverage on a minimal app, so a new verb cannot slip through


def _minimal_gated_app() -> FastAPI:
    app = FastAPI()
    register_middleware(app, Config())

    @app.api_route("/echo", methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"])
    async def echo() -> PlainTextResponse:
        return PlainTextResponse("ok")

    return app


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_every_non_safe_verb_is_denied_for_demo_token(method: str, demo_token: str) -> None:
    client = TestClient(_minimal_gated_app())

    response = client.request(method, "/echo", headers=_bearer(demo_token))

    assert response.status_code == 403
    assert response.json()["detail"] == DEMO_BLOCKED_DETAIL


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_every_safe_verb_is_allowed_for_demo_token(method: str, demo_token: str) -> None:
    client = TestClient(_minimal_gated_app())

    response = client.request(method, "/echo", headers=_bearer(demo_token))

    assert response.status_code != 403


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_every_non_safe_verb_is_allowed_for_real_token(method: str, real_token: str) -> None:
    client = TestClient(_minimal_gated_app())

    response = client.request(method, "/echo", headers=_bearer(real_token))

    assert response.status_code != 403


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_every_non_safe_verb_is_allowed_with_no_token(method: str) -> None:
    client = TestClient(_minimal_gated_app())

    response = client.request(method, "/echo")

    assert response.status_code != 403
