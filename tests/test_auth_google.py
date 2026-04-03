from fastapi.testclient import TestClient

from backend.app import create_app


def test_token_requires_configured_email():
    app = create_app()
    client = TestClient(app)

    # Token mapped to user@example.com should succeed (see mock in conftest)
    ok = client.post("/token", json={"id_token": "good"})
    assert ok.status_code == 200
    assert "access_token" in ok.json()

    # Token mapped to other@example.com should be rejected
    bad = client.post("/token", json={"id_token": "other"})
    # Unauthorized email returns 403 Forbidden: request understood but not allowed
    assert bad.status_code == 403


def test_token_rejects_malformed_json_body():
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/token",
        content="{not-json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid JSON body"}


def test_token_accepts_form_username_login():
    app = create_app()
    client = TestClient(app)

    response = client.post("/token", data={"username": "testuser", "password": "password"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert "access_token" in payload
