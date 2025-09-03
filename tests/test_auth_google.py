from fastapi.testclient import TestClient

from backend.app import create_app


def test_token_requires_configured_email():
    app = create_app()
    client = TestClient(app)

    # Token mapped to lucy@example.com should succeed (see mock in conftest)
    ok = client.post("/token", json={"id_token": "good"})
    assert ok.status_code == 200
    assert "access_token" in ok.json()

    # Token mapped to other@example.com should be rejected
    bad = client.post("/token", json={"id_token": "other"})
    # Unauthorized email returns 403 Forbidden: request understood but not allowed
    assert bad.status_code == 403
