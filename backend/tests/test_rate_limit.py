from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app import create_app
from backend.config import config


def test_rate_limit_enforced(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    app.state.limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["2/minute"],
        storage_uri="memory://",
    )
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 429
