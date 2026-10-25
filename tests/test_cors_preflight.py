from pathlib import Path

import yaml
from fastapi.testclient import TestClient

import backend.config as config_module
from backend.app import create_app
from backend.config import config, reload_config


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
    2568 onto 2569+, so a dev machine running several checkouts cannot rely on
    the enumerated list alone.
    """
    monkeypatch.setattr(config, "cors_origins", ["http://localhost:3000"])
    monkeypatch.setattr(config, "cors_origin_regex", r"^http://localhost:2[5-9]\d{2}$")
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    with TestClient(app) as client:
        origin = "http://localhost:2569"
        resp = client.options(
            "/health",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == origin


def test_cors_preflight_regex_does_not_widen_beyond_pattern(monkeypatch):
    """Origins outside the pattern stay blocked -- the regex must not act as '*'."""
    monkeypatch.setattr(config, "cors_origins", ["http://localhost:3000"])
    monkeypatch.setattr(config, "cors_origin_regex", r"^http://localhost:2[5-9]\d{2}$")
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    with TestClient(app) as client:
        for origin in (
            "https://evil.com",
            "http://localhost:6468",
            "http://evil.localhost:2569",
        ):
            resp = client.options(
                "/health",
                headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
            )
            assert "access-control-allow-origin" not in resp.headers, origin


def test_cors_preflight_allowlist_still_works_with_regex_set(monkeypatch):
    """The explicit list and the regex are ORed, so neither disables the other."""
    monkeypatch.setattr(config, "cors_origins", ["https://app.allotmint.io"])
    monkeypatch.setattr(config, "cors_origin_regex", r"^http://localhost:2[5-9]\d{2}$")
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
                "Origin": "http://localhost:2569",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert "access-control-allow-origin" not in resp.headers


def test_cors_exposes_the_admin_warming_header(monkeypatch):
    """The admin pages read the partial-while-warming marker cross-origin (#10754)."""
    from backend.common.admin_cache_state import WARMING_HEADER

    origin = "https://app.allotmint.io"
    monkeypatch.setattr(config, "cors_origins", [origin])
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health", headers={"Origin": origin})
    exposed = [h.strip().lower() for h in resp.headers["access-control-expose-headers"].split(",")]
    assert WARMING_HEADER.lower() in exposed


def _write_config_with_origin_regex(tmp_path: Path, pattern: str) -> Path:
    """Copy the project config.yaml with ``server.cors.origin_regex`` set.

    ``repo_root`` is pinned to the real project root so every other path still
    resolves exactly as with the checked-in file; only the regex differs.
    """
    project_path = config_module._project_config_path()
    data = yaml.safe_load(project_path.read_text(encoding="utf-8"))
    data["paths"]["repo_root"] = str(project_path.parent)
    data["server"].setdefault("cors", {})["origin_regex"] = pattern
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_cors_preflight_regex_from_config_file(monkeypatch, tmp_path):
    """A regex set in config.yaml (not the env) reaches the middleware via create_app (#7708)."""
    config_path = _write_config_with_origin_regex(tmp_path, r"^http://localhost:(3000|5\d{3})$")
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
    monkeypatch.setattr(config, "cors_origins", ["https://app.allotmint.io"])
    # None is not carried over as a runtime override, so the reload inside
    # create_app must take the regex from the file.
    monkeypatch.setattr(config, "cors_origin_regex", None)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    try:
        with monkeypatch.context() as m:
            m.setattr(config_module, "_project_config_path", lambda: config_path)
            app = create_app()
        assert config.cors_origin_regex == r"^http://localhost:(3000|5\d{3})$"
        with TestClient(app) as client:
            allowed = {
                origin: client.options(
                    "/health",
                    headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
                ).headers.get("access-control-allow-origin")
                for origin in (
                    "http://localhost:5173",
                    "http://evil.localhost:5174",
                    "https://app.allotmint.io",
                )
            }
    finally:
        reload_config()
    assert allowed == {
        "http://localhost:5173": "http://localhost:5173",
        "http://evil.localhost:5174": None,
        "https://app.allotmint.io": "https://app.allotmint.io",
    }
