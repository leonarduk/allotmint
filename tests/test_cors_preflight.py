from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config


def test_cors_preflight(monkeypatch):
    origin = "https://app.allotmint.io"
    monkeypatch.setattr(config, "cors_origins", [origin])
    # Skip snapshot warming so tests run quickly without side effects.
    # monkeypatch reverts this change after the test to avoid leaking config.
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    with TestClient(app) as client:
        headers = {
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        }
        resp = client.options("/health", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == origin
    allow_methods = [m.strip() for m in resp.headers["access-control-allow-methods"].split(",")]
    assert "POST" in allow_methods
    assert "*" not in allow_methods
    allow_headers = [h.strip() for h in resp.headers["access-control-allow-headers"].split(",")]
    assert "Authorization" in allow_headers
    assert "Content-Type" in allow_headers
    assert "*" not in allow_headers


def test_cors_preflight_respects_configured_origin(monkeypatch):
    origin = "https://app.allotmint.io"
    monkeypatch.setattr(config, "cors_origins", ["http://localhost:3000", origin])
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    with TestClient(app) as client:
        headers = {
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        }
        resp = client.options("/health", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == origin


def test_cors_preflight_allows_origin_matching_regex(monkeypatch):
    """A port not in the allowlist is accepted when the regex covers it.

    This is the case the regex exists for: vite walks past an already-taken
    5173 onto 5174+, so a dev machine running several checkouts cannot rely on
    the enumerated list alone.
    """
    monkeypatch.setattr(config, "cors_origins", ["http://localhost:3000"])
    monkeypatch.setattr(config, "cors_origin_regex", r"^http://localhost:5\d{3}$")
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    with TestClient(app) as client:
        origin = "http://localhost:5174"
        resp = client.options(
            "/health",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == origin


def test_cors_preflight_regex_does_not_widen_beyond_pattern(monkeypatch):
    """Origins outside the pattern stay blocked -- the regex must not act as '*'."""
    monkeypatch.setattr(config, "cors_origins", ["http://localhost:3000"])
    monkeypatch.setattr(config, "cors_origin_regex", r"^http://localhost:5\d{3}$")
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    with TestClient(app) as client:
        for origin in (
            "https://evil.com",
            "http://localhost:8000",
            "http://evil.localhost:5174",
        ):
            resp = client.options(
                "/health",
                headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
            )
            assert "access-control-allow-origin" not in resp.headers, origin


def test_cors_preflight_allowlist_still_works_with_regex_set(monkeypatch):
    """The explicit list and the regex are ORed, so neither disables the other."""
    monkeypatch.setattr(config, "cors_origins", ["https://app.allotmint.io"])
    monkeypatch.setattr(config, "cors_origin_regex", r"^http://localhost:5\d{3}$")
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    with TestClient(app) as client:
        origin = "https://app.allotmint.io"
        resp = client.options(
            "/health",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == origin


def test_cors_preflight_unset_regex_leaves_policy_unchanged(monkeypatch):
    """With no regex configured, behaviour is exactly the pre-existing allowlist."""
    monkeypatch.setattr(config, "cors_origins", ["http://localhost:3000"])
    monkeypatch.setattr(config, "cors_origin_regex", None)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    with TestClient(app) as client:
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5174",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert "access-control-allow-origin" not in resp.headers
