from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config


def test_cors_preflight(monkeypatch):
    monkeypatch.setattr(config, "cors_origins", ["https://app.allotmint.io"])
    # Skip snapshot warming so tests run quickly without side effects.
    # monkeypatch reverts this change after the test to avoid leaking config.
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    with TestClient(app) as client:
        headers = {
            "Origin": "https://app.allotmint.io",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        }
        resp = client.options("/health", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "https://app.allotmint.io"
    allow_methods = [m.strip() for m in resp.headers["access-control-allow-methods"].split(",")]
    assert "POST" in allow_methods
    assert "*" not in allow_methods
    allow_headers = [h.strip() for h in resp.headers["access-control-allow-headers"].split(",")]
    assert "Authorization" in allow_headers
    assert "Content-Type" in allow_headers
    assert "*" not in allow_headers
