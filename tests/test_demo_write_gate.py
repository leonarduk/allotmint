"""Integration tests for the global demo scope/write gate (#7407, #7522 follow-up).

Exercises ``backend.bootstrap.middleware.register_middleware``'s
``demo_scope_gate`` HTTP middleware. A demo-scoped token (see
``backend.auth.create_demo_access_token`` / ``decode_demo_token``, #7405) must:

1. Never reach a mutating handler, on *any* router, regardless of whether
   that router carries a router-level ``Depends(auth.get_current_user)``.
2. Resolve to ``is_demo_request() == True`` / ``current_user == <owner>`` for
   *every* request -- including a ``GET`` on a route with no auth dependency
   at all -- not just requests that happen to hit
   ``get_current_user``/``get_active_user`` as a FastAPI dependency. This was
   found live in production (post #7404-#7411, #7522): a valid demo-link
   token could read every real owner's full portfolio via ``GET /owners`` and
   the default "all owners" group dashboard, because neither route declares
   ``Depends(get_current_user)`` and the deployed Lambda runs
   ``disable_auth=True`` (so ``portfolio_router``'s router-level dependency
   list is also empty -- see ``backend/bootstrap/routers.py``). Every
   ``is_demo_request()``-based owner-scoping check downstream
   (``ensure_owner_access``, ``_list_aws_plots``/``_list_local_plots``) was
   therefore silently a no-op for those routes. The gate now resolves demo
   identity itself, unconditionally, before any routing happens, closing
   that gap regardless of a given route's own dependency wiring.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from backend import auth
from backend.app import create_app
from backend.bootstrap.middleware import register_middleware
from backend.config import Config, config

DEMO_BLOCKED_DETAIL = "Demo access is read-only"
DEMO_LINK_INVALID_DETAIL = "Invalid authentication credentials"


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


# --- Safe methods: never write-blocked, but still identity-resolved --------


def test_get_with_demo_token_returns_401_when_demo_link_disabled(
    client: TestClient, demo_token: str
) -> None:
    """A GET is never rejected by the *write* gate (never 403/DEMO_BLOCKED_DETAIL)
    -- but it is no longer waved through unconditionally either. With
    demo_link_enabled left at its default False, the gate's own
    ``_resolve_demo_request`` call now rejects the token with 401 *before*
    routing ever runs, exactly as a real Cognito-gated route would reject an
    invalid credential at the boundary -- regardless of whether a matching
    route exists. This is the corrected behaviour: previously this GET would
    have reached routing and 404'd, silently leaving demo_link_enabled
    unchecked for any route lacking its own auth dependency."""

    response = client.get("/definitely-not-a-real-route", headers=_bearer(demo_token))

    assert response.status_code == 401
    assert response.json()["detail"] == DEMO_LINK_INVALID_DETAIL


def test_get_with_demo_token_reaches_routing_when_demo_link_enabled(
    monkeypatch: pytest.MonkeyPatch, demo_token: str
) -> None:
    """With demo_link enabled and the owner matching, the gate lets a GET
    proceed to routing (never blocked by the write gate; not rejected by
    identity resolution either) -- the nonexistent route then produces an
    ordinary 404, proving the gate itself did not reject the request."""

    monkeypatch.setenv("TESTING", "1")
    app = create_app()
    # Patched *after* create_app(): create_app()'s own config loading
    # (backend.bootstrap.load_runtime_config / reload_config) mutates the
    # same backend.config.config singleton in place, so patching before
    # create_app() runs gets silently overwritten by its reload. auth.py's
    # _resolve_demo_request reads the singleton fresh on every call, so
    # patching after app construction (right before the request) is what
    # actually takes effect for the middleware's per-request check.
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)

    with TestClient(app) as enabled_client:
        response = enabled_client.get("/definitely-not-a-real-route", headers=_bearer(demo_token))

    assert response.status_code == 404


def test_options_preflight_with_demo_token_is_not_blocked(client: TestClient, demo_token: str) -> None:
    """OPTIONS is excluded from identity resolution entirely (not just the
    write-block), regardless of demo_link_enabled -- left at its default
    False here, which would 401 any other method carrying this token. A
    browser's CORS preflight never carries real credentials, so gating it on
    demo-link config would break CORS for reasons unrelated to the real
    request that follows (mirrors why API Gateway's own OPTIONS routes are
    unauthenticated -- see cdk/stacks/backend_lambda_stack.py)."""

    response = client.options(
        "/transactions",
        headers={
            **_bearer(demo_token),
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code != 403
    assert response.status_code != 401


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
def test_every_safe_verb_is_allowed_for_demo_token(
    monkeypatch: pytest.MonkeyPatch, method: str, demo_token: str
) -> None:
    """A safe verb reaches the real handler (200, not just "not 403") when
    demo_link is enabled and the token's owner matches -- a weaker "!= 403"
    assertion would not have caught GET/HEAD being silently 401'd by the
    identity-resolution half of this gate when demo_link is disabled."""

    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    client = TestClient(_minimal_gated_app())

    response = client.request(method, "/echo", headers=_bearer(demo_token))

    assert response.status_code != 403
    assert response.status_code != 401


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


# --- Regression: demo identity resolves for every request, not just routes
# --- that happen to declare Depends(get_current_user)/get_active_user -------


def _no_dependency_app() -> FastAPI:
    """A GET route with *no* auth dependency of any kind -- the exact shape
    of the routes that leaked real owner data in production (GET /owners'
    disable_auth branch, GET /portfolio-group/{slug} and everything under
    it): none of them call Depends(get_current_user)/get_active_user, so
    before this fix nothing ever set the demo ContextVars for them."""

    app = FastAPI()
    register_middleware(app, Config())

    @app.get("/no-deps-at-all")
    async def handler() -> dict:
        return {"is_demo": auth.is_demo_request(), "current_user": auth.current_user.get()}

    return app


def test_demo_identity_resolves_without_any_route_dependency(
    monkeypatch: pytest.MonkeyPatch, demo_token: str
) -> None:
    """The core regression test: is_demo_request()/current_user must be
    correctly populated for a GET route that declares no auth dependency at
    all, once demo_link is enabled and the token's owner matches. Before this
    fix, is_demo_request() stayed False here (the ContextVar was only ever
    set inside get_current_user/get_active_user, and nothing on this route
    calls either), so every owner-scoping check built on top of it
    (ensure_owner_access, _list_aws_plots/_list_local_plots) was a silent
    no-op -- a demo-scoped token could read every real owner's data."""

    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    client = TestClient(_no_dependency_app())

    response = client.get("/no-deps-at-all", headers=_bearer(demo_token))

    assert response.status_code == 200
    assert response.json() == {"is_demo": True, "current_user": "demo"}


def test_demo_identity_does_not_leak_into_a_later_unrelated_request(
    monkeypatch: pytest.MonkeyPatch, demo_token: str
) -> None:
    """demo_readonly is reset to False at the top of *every* request
    (demo-scoped or not), mirroring get_current_user/get_active_user's own
    reset (backend/auth.py) -- this middleware is now the only place
    guaranteed to run for every request, so it must do that reset itself. A
    Lambda execution environment can be reused across invocations; without
    an unconditional reset here, a demo request's True could leak into a
    later, unrelated request that also happens not to invoke
    get_current_user/get_active_user."""

    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "demo", raising=False)
    client = TestClient(_no_dependency_app())

    demo_response = client.get("/no-deps-at-all", headers=_bearer(demo_token))
    assert demo_response.json()["is_demo"] is True

    plain_response = client.get("/no-deps-at-all")
    assert plain_response.json() == {"is_demo": False, "current_user": None}


def test_demo_token_for_wrong_owner_is_rejected_before_routing(
    monkeypatch: pytest.MonkeyPatch, demo_token: str
) -> None:
    """demo_token is minted for owner "demo" (see the module-level fixture);
    a deployment configured for a *different* demo_link_owner must reject it
    with 401 before routing, not silently resolve it -- otherwise a token
    minted before a demo_link_owner change would still work."""

    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", "someone-else", raising=False)
    client = TestClient(_no_dependency_app())

    response = client.get("/no-deps-at-all", headers=_bearer(demo_token))

    assert response.status_code == 401
    assert response.json()["detail"] == DEMO_LINK_INVALID_DETAIL
