import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import backend.auth as auth
from backend.app import create_app
from backend.config import config


def test_health_env_variable(monkeypatch):
    monkeypatch.setattr(config, "app_env", "staging")
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    with patch("backend.common.portfolio_utils.refresh_snapshot_async") as mock_refresh:
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/health")
    mock_refresh.assert_called_once_with(days=30)
    assert resp.status_code == 200
    assert resp.json()["env"] == "staging"


@pytest.mark.asyncio
async def test_startup_warms_snapshot(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", False)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    with (
        patch("backend.common.portfolio_utils.refresh_snapshot_async") as mock_refresh,
        patch("backend.common.portfolio_utils._load_snapshot", return_value=({}, None)) as mock_load,
        patch("backend.common.portfolio_utils.refresh_snapshot_in_memory") as mock_mem,
        patch("backend.common.instrument_api.update_latest_prices_from_snapshot") as mock_update,
        patch("backend.common.instrument_api.prime_latest_prices") as mock_prime,
    ):
        app = create_app()
        # prime_latest_prices now runs inside a background asyncio Task
        # rather than synchronously. Use the async lifespan directly and
        # await the task so the assertion below can observe the call.
        async with app.router.lifespan_context(app):
            tasks = getattr(app.state, "background_tasks", [])
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    mock_refresh.assert_called_once_with(days=30)
    mock_load.assert_called_once_with()
    mock_mem.assert_called_once_with({}, None)
    mock_update.assert_called_once_with({})
    mock_prime.assert_called_once()


def test_skip_snapshot_warm(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    with (
        patch("backend.common.portfolio_utils.refresh_snapshot_async") as mock_refresh,
        patch("backend.common.portfolio_utils._load_snapshot") as mock_load,
        patch("backend.common.instrument_api.update_latest_prices_from_snapshot") as mock_update,
        patch("backend.common.instrument_api.prime_latest_prices") as mock_prime,
    ):
        app = create_app()
        with TestClient(app):
            pass
    mock_refresh.assert_called_once_with(days=30)
    mock_load.assert_not_called()
    mock_update.assert_not_called()
    mock_prime.assert_not_called()


def test_create_app_registers_rebalance_route(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    with patch("backend.common.portfolio_utils.refresh_snapshot_async"):
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/rebalance", json={"actual": {}, "target": {}})
    # 404 means the route was never registered; any other status confirms it is wired up
    assert resp.status_code != 404


def test_docs_url_is_removed(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    with patch("backend.common.portfolio_utils.refresh_snapshot_async"):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/docs")
    assert resp.status_code == 404


def test_api_console_no_auth_local_dev(monkeypatch):
    """GET /api-console returns 200 (HTML) in local dev without any dependency overrides.

    When disable_auth=True and no ADMIN_EMAILS is configured, the admin gate
    should allow unauthenticated visitors through — no token, no
    local_login_email, no dependency_overrides required.
    """
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    with patch("backend.common.portfolio_utils.refresh_snapshot_async"):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/api-console")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_api_console_accessible_when_auth_disabled(monkeypatch):
    # When auth is disabled the admin check is bypassed; use dependency_overrides
    # so get_current_user returns a user without a real JWT token.
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    monkeypatch.setattr(config, "disable_auth", True)
    with patch("backend.common.portfolio_utils.refresh_snapshot_async"):
        app = create_app()
        app.dependency_overrides[auth.get_current_user] = lambda: "dev@example.com"
        with TestClient(app) as client:
            resp = client.get("/api-console")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_api_console_admin_allowlist_enforced_when_auth_disabled(monkeypatch):
    """ADMIN_EMAILS must still be enforced when disable_auth=True and the
    caller presents no valid token.

    DISABLE_AUTH=true is set on the production Lambda (API Gateway handles
    Cognito auth upstream), so this combination is the real production
    configuration whenever ADMIN_EMAILS is also set. This test exercises the
    dependency chain end-to-end (no dependency_overrides, matching
    ``test_api_console_no_auth_local_dev``) with a missing/invalid bearer
    token to confirm the admin allowlist gate is not silently bypassed just
    because auth is disabled.
    """
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "local_login_email", None)
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    with patch("backend.common.portfolio_utils.refresh_snapshot_async"):
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            # No Authorization header at all: missing token.
            resp_missing = client.get("/api-console")
            # An invalid/garbage bearer token that cannot be decoded.
            resp_invalid = client.get(
                "/api-console",
                headers={"Authorization": "Bearer not-a-real-token"},
            )
    # Neither request authenticates as an admin, so both must be rejected
    # rather than falling through to the local-dev bypass.
    assert resp_missing.status_code == 403
    assert resp_invalid.status_code in (401, 403)


@pytest.mark.parametrize(
    "admin_emails,disable_auth,email,expected_status",
    [
        # allowlist configured: enforced regardless of disable_auth
        ("admin@example.com", False, "admin@example.com", 200),
        ("admin@example.com", False, "other@example.com", 403),
        # DISABLE_AUTH=true is set on the production Lambda (API GW handles Cognito auth)
        # and must NOT bypass the admin allowlist when ADMIN_EMAILS is configured.
        ("admin@example.com", True, "admin@example.com", 200),
        ("admin@example.com", True, "other@example.com", 403),
        # case-insensitivity: both sides are lowercased before comparison
        ("Admin@Example.COM", False, "admin@example.com", 200),
        # no allowlist in prod-like env: deny all (misconfiguration guard)
        ("", False, "anyone@example.com", 403),
        # no allowlist + disable_auth=True → local dev bypass, allow through
        ("", True, "anyone@example.com", 200),
    ],
)
def test_api_console_admin_check(monkeypatch, admin_emails, disable_auth, email, expected_status):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    monkeypatch.setattr(config, "disable_auth", disable_auth)
    monkeypatch.setenv("ADMIN_EMAILS", admin_emails)
    with patch("backend.common.portfolio_utils.refresh_snapshot_async"):
        app = create_app()
        app.dependency_overrides[auth.get_current_user] = lambda: email
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api-console")
    assert resp.status_code == expected_status


def _whoami_app(monkeypatch, *, admin_emails="admin@example.com", disable_auth=True):
    """Build an app configured for /whoami tests with the admin allowlist set."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    monkeypatch.setattr(config, "disable_auth", disable_auth)
    monkeypatch.setenv("ADMIN_EMAILS", admin_emails)
    with patch("backend.common.portfolio_utils.refresh_snapshot_async"):
        return create_app()


def test_whoami_requires_admin(monkeypatch):
    """Non-admin users must never see decoded token claims."""
    app = _whoami_app(monkeypatch)
    app.dependency_overrides[auth.get_current_user] = lambda: "other@example.com"
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/whoami")
    assert resp.status_code == 403


def test_whoami_returns_claims_for_admin(monkeypatch):
    """An admin sees the allowlisted claim subset and the allowed-email result."""
    import jwt

    app = _whoami_app(monkeypatch)
    app.dependency_overrides[auth.get_current_user] = lambda: "admin@example.com"
    monkeypatch.setattr(auth, "_allowed_emails", lambda: {"admin@example.com"})

    token = jwt.encode(
        {
            "sub": "cognito-sub-123",
            "email": "admin@example.com",
            "exp": 9999999999,
            "iss": "https://cognito-idp.eu-west-2.amazonaws.com/pool",
            "token_use": "id",
            "aud": "client-abc",
            "secret_claim": "should-not-leak",
        },
        "unverified-signature-secret-not-checked-by-whoami",
        algorithm="HS256",
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_present"] is True
    assert body["allowed_email_match"] is True
    assert body["claims"]["email"] == "admin@example.com"
    assert body["claims"]["token_use"] == "id"
    assert body["claims"]["aud"] == "client-abc"
    # Only the allowlisted claims are echoed; unexpected claims are dropped.
    assert "secret_claim" not in body["claims"]
    assert "note" in body


def test_whoami_reports_token_absent(monkeypatch):
    """With no bearer token the response reports token_present=False."""
    app = _whoami_app(monkeypatch)
    app.dependency_overrides[auth.get_current_user] = lambda: "admin@example.com"
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/whoami")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_present"] is False
    assert body["claims"] == {}
    assert body["allowed_email_match"] is False


def test_whoami_malformed_token(monkeypatch):
    """A bearer token that isn't a decodable JWT still reports token_present=True
    but with no claims and no allowed-email match."""
    app = _whoami_app(monkeypatch)
    app.dependency_overrides[auth.get_current_user] = lambda: "admin@example.com"
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/whoami", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_present"] is True
    assert body["claims"] == {}
    assert body["allowed_email_match"] is False


def test_whoami_email_not_in_admin_emails(monkeypatch):
    """A validly-decoded token whose email is absent from ADMIN_EMAILS reports
    allowed_email_match=False even though the caller passed the admin gate."""
    import jwt

    app = _whoami_app(monkeypatch)
    app.dependency_overrides[auth.get_current_user] = lambda: "admin@example.com"
    monkeypatch.setattr(auth, "_allowed_emails", lambda: {"admin@example.com"})

    token = jwt.encode(
        {
            "sub": "cognito-sub-456",
            "email": "not-allowed@example.com",
            "exp": 9999999999,
        },
        "unverified-signature-secret-not-checked-by-whoami",
        algorithm="HS256",
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_present"] is True
    assert body["claims"]["email"] == "not-allowed@example.com"
    assert body["allowed_email_match"] is False


def test_health_returns_200_when_prime_latest_prices_fails(monkeypatch):
    """App must still serve /health even when optional snapshot warm-up fails."""
    monkeypatch.setattr(config, "skip_snapshot_warm", False)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)

    def _fail():
        raise RuntimeError("simulated network failure on cold start")

    with (
        patch("backend.common.portfolio_utils.refresh_snapshot_async"),
        patch("backend.common.portfolio_utils._load_snapshot", return_value=({}, None)),
        patch("backend.common.portfolio_utils.refresh_snapshot_in_memory"),
        patch("backend.common.instrument_api.update_latest_prices_from_snapshot"),
        patch("backend.common.instrument_api.prime_latest_prices", side_effect=_fail),
    ):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/health")
    assert resp.status_code == 200


def test_health_returns_200_when_update_latest_prices_fails(monkeypatch):
    """App must still serve /health even when update_latest_prices raises."""
    monkeypatch.setattr(config, "skip_snapshot_warm", False)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)

    def _fail(_snapshot):
        raise RuntimeError("simulated update_latest_prices failure")

    with (
        patch("backend.common.portfolio_utils.refresh_snapshot_async"),
        patch("backend.common.portfolio_utils._load_snapshot", return_value=({}, None)),
        patch("backend.common.portfolio_utils.refresh_snapshot_in_memory"),
        patch(
            "backend.common.instrument_api.update_latest_prices_from_snapshot",
            side_effect=_fail,
        ),
        patch("backend.common.instrument_api.prime_latest_prices"),
    ):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/health")
    assert resp.status_code == 200


def test_api_console_returns_401_when_unauthenticated(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    with patch("backend.common.portfolio_utils.refresh_snapshot_async"):
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api-console")
    assert resp.status_code == 401


def test_openapi_json_still_accessible(monkeypatch):
    """/openapi.json must remain reachable after docs_url is set to None."""
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    with patch("backend.common.portfolio_utils.refresh_snapshot_async"):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"] == "Allotmint API"


def test_health_returns_expected_body_without_auth_header(monkeypatch):
    """GET /health must positively return its documented body with no
    Authorization header at all, not merely avoid a 401.

    Auth is deliberately left enabled (disable_auth=False) so this test
    proves the route itself carries no auth dependency, rather than passing
    only because auth checks were disabled for the whole app (#5329).
    """
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setattr(config, "app_env", "test-env")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    with patch("backend.common.portfolio_utils.refresh_snapshot_async"):
        app = create_app()
        with TestClient(app) as client:
            assert "Authorization" not in client.headers
            resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "env": "test-env"}


def test_config_get_returns_expected_body_without_auth_header(monkeypatch):
    """GET /config must positively return the serialised configuration with
    no Authorization header, since it is the frontend's pre-auth bootstrap
    endpoint used to determine whether auth is required at all (#5329).
    """
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    monkeypatch.setattr(config, "disable_auth", False)
    # google_auth_enabled/google_client_id are re-derived from the environment
    # by load_runtime_config() on every create_app() call (they are not in
    # backend/bootstrap/config.py's _OVERRIDE_ATTRS), so set them via env vars
    # rather than monkeypatch.setattr(config, ...), which would be discarded.
    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-123")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    with patch("backend.common.portfolio_utils.refresh_snapshot_async"):
        app = create_app()
        with TestClient(app) as client:
            assert "Authorization" not in client.headers
            resp = client.get("/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["disable_auth"] is False
    assert body["google_auth_enabled"] is True
    assert body["google_client_id"] == "client-123"


def test_token_google_exchanges_token_without_auth_header(monkeypatch):
    """POST /token/google must positively exchange a Google ID token for an
    app JWT with no Authorization header present, since callers reach this
    endpoint with no session of their own yet (#5329, see also #4240).

    The Google verification itself is mocked out (as in
    tests/test_google_auth.py::test_google_token_flow) so the test exercises
    the route's response shape without depending on live Google network
    calls.
    """
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "snapshot_warm_days", 30)
    monkeypatch.setattr(config, "disable_auth", False)
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setattr(auth, "verify_google_token", lambda token: "user@example.com")
    with patch("backend.common.portfolio_utils.refresh_snapshot_async"):
        app = create_app()
        with TestClient(app) as client:
            assert "Authorization" not in client.headers
            resp = client.post("/token/google", json={"token": "google-id-token"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]
