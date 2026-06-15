import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import signup as signup_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A test client with the signup router and an isolated request store.

    ``resolve_accounts_root`` is patched to point at a temp directory so the
    handler never writes into the repo's ``data/`` tree.
    """

    accounts_root = tmp_path / "accounts"
    monkeypatch.setattr(
        signup_module,
        "resolve_accounts_root",
        lambda request, allow_missing=False: accounts_root,
    )
    monkeypatch.setenv("SIGNUP_ADMIN_EMAIL", "admin@example.com")

    app = FastAPI()
    app.include_router(signup_module.router)
    return TestClient(app), tmp_path


def _capture_email(monkeypatch):
    sent = {}

    def fake_send(admin_email, notification):
        sent["admin_email"] = admin_email
        sent["notification"] = notification

    monkeypatch.setattr(signup_module, "send_signup_admin_email", fake_send)
    return sent


def test_valid_request_records_and_notifies(client, monkeypatch):
    test_client, tmp_path = client
    sent = _capture_email(monkeypatch)

    resp = test_client.post(
        "/signup/request",
        json={"name": "Jane", "email": "Jane@Example.com", "note": "hi"},
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok",
        "message": "If your request is valid, an administrator has been notified.",
    }

    # Persisted exactly one pending request with the normalised email.
    store = tmp_path / "signup_requests"
    files = list(store.glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text())
    assert saved["email"] == "jane@example.com"
    assert saved["status"] == "pending"

    # Admin was notified with approve/reject links.
    assert sent["admin_email"] == "admin@example.com"
    assert sent["notification"].request_id == saved["id"]
    assert "/signup/approve" in sent["notification"].approve_url
    assert "/signup/reject" in sent["notification"].reject_url


def test_invalid_payload_returns_400(client, monkeypatch):
    test_client, _ = client
    _capture_email(monkeypatch)

    resp = test_client.post("/signup/request", json={"name": "", "email": "nope"})
    assert resp.status_code == 400


def test_missing_base_url_warns_but_still_notifies(client, monkeypatch, caplog):
    test_client, _ = client
    sent = _capture_email(monkeypatch)
    monkeypatch.delenv("SIGNUP_APPROVAL_BASE_URL", raising=False)

    with caplog.at_level("WARNING"):
        resp = test_client.post(
            "/signup/request", json={"name": "Jane", "email": "jane@example.com"}
        )

    assert resp.status_code == 200
    assert sent["notification"].approve_url.startswith("/signup/approve")
    assert any("SIGNUP_APPROVAL_BASE_URL" in r.message for r in caplog.records)


def test_existing_and_new_emails_are_indistinguishable(client, monkeypatch):
    test_client, _ = client
    _capture_email(monkeypatch)

    first = test_client.post(
        "/signup/request", json={"name": "Existing", "email": "alice@example.com"}
    )
    second = test_client.post(
        "/signup/request", json={"name": "New", "email": "brandnew@example.com"}
    )

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_missing_admin_email_returns_503(client, monkeypatch):
    test_client, _ = client
    _capture_email(monkeypatch)
    monkeypatch.delenv("SIGNUP_ADMIN_EMAIL", raising=False)

    resp = test_client.post("/signup/request", json={"name": "Jane", "email": "jane@example.com"})
    assert resp.status_code == 503


def test_email_send_failure_is_not_swallowed(client, monkeypatch):
    test_client, _ = client

    def boom(admin_email, notification):
        raise RuntimeError("SES down")

    monkeypatch.setattr(signup_module, "send_signup_admin_email", boom)

    resp = test_client.post("/signup/request", json={"name": "Jane", "email": "jane@example.com"})
    assert resp.status_code == 502
