import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.common import signup_requests
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
        resp = test_client.post("/signup/request", json={"name": "Jane", "email": "jane@example.com"})

    assert resp.status_code == 200
    assert sent["notification"].approve_url.startswith("/signup/approve")
    assert any("SIGNUP_APPROVAL_BASE_URL" in r.message for r in caplog.records)


def test_existing_and_new_emails_are_indistinguishable(client, monkeypatch):
    test_client, _ = client
    _capture_email(monkeypatch)

    first = test_client.post("/signup/request", json={"name": "Existing", "email": "alice@example.com"})
    second = test_client.post("/signup/request", json={"name": "New", "email": "brandnew@example.com"})

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


# ---------------------------------------------------------------------------
# Approval flow (#4352)
# ---------------------------------------------------------------------------


class _FakeStore:
    """Minimal writable-store stand-in recording ensure_owner calls."""

    is_global = False

    def __init__(self):
        self.ensured = []

    def ensure_owner(self, owner):
        self.ensured.append(owner)


def _pending_request(tmp_path, email="jane@example.com", name="Jane Doe"):
    """Create a pending request in the router's store and return (id, token)."""

    store_dir = signup_requests.signup_requests_dir(tmp_path)
    record, token = signup_requests.create_signup_request(name, email, "", store_dir)
    return record.id, token


def _capture_user_email(monkeypatch):
    sent = {}

    def fake_send(user_email, name, login_url):
        sent["user_email"] = user_email
        sent["name"] = name
        sent["login_url"] = login_url

    monkeypatch.setattr(signup_module, "send_signup_approved_email", fake_send)
    return sent


def _stub_store(monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr(signup_module, "resolve_writable_store", lambda request: store)
    return store


def test_approve_provisions_owner_and_notifies_user(client, monkeypatch):
    test_client, tmp_path = client
    sent = _capture_user_email(monkeypatch)
    store = _stub_store(monkeypatch)
    monkeypatch.setenv("SIGNUP_LOGIN_URL", "https://allotmint.example/login")

    request_id, token = _pending_request(tmp_path)

    resp = test_client.post(f"/signup/approve?id={request_id}&token={token}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "approved", "owner": "jane"}

    # Owner scaffolded and email written so auth._allowed_emails admits them.
    person = json.loads((tmp_path / "accounts" / "jane" / "person.json").read_text())
    assert person["email"] == "jane@example.com"
    assert store.ensured == ["jane"]

    # User was emailed their login-ready notice.
    assert sent["user_email"] == "jane@example.com"
    assert sent["login_url"] == "https://allotmint.example/login"

    # Request is consumed.
    store_dir = signup_requests.signup_requests_dir(tmp_path)
    assert json.loads((store_dir / f"{request_id}.json").read_text())["status"] == "approved"


def test_approved_email_is_in_allowed_emails(client, monkeypatch):
    """End-to-end: an approved user's email becomes part of the login allowlist."""

    test_client, tmp_path = client
    _capture_user_email(monkeypatch)
    _stub_store(monkeypatch)

    request_id, token = _pending_request(tmp_path)
    resp = test_client.post(f"/signup/approve?id={request_id}&token={token}")
    assert resp.status_code == 200

    import backend.auth as auth

    monkeypatch.setattr(auth.config, "accounts_root", str(tmp_path / "accounts"))
    monkeypatch.setattr(auth.config, "app_env", "local", raising=False)
    assert "jane@example.com" in auth._allowed_emails()


def test_approve_is_single_use(client, monkeypatch):
    test_client, tmp_path = client
    _capture_user_email(monkeypatch)
    _stub_store(monkeypatch)

    request_id, token = _pending_request(tmp_path)
    first = test_client.post(f"/signup/approve?id={request_id}&token={token}")
    assert first.status_code == 200

    second = test_client.post(f"/signup/approve?id={request_id}&token={token}")
    assert second.status_code == 409


def test_approve_invalid_token_rejected(client, monkeypatch):
    test_client, tmp_path = client
    _capture_user_email(monkeypatch)
    _stub_store(monkeypatch)

    request_id, _ = _pending_request(tmp_path)
    resp = test_client.post(f"/signup/approve?id={request_id}&token=not-the-token")
    assert resp.status_code == 400
    # Nothing was provisioned.
    assert not (tmp_path / "accounts" / "jane").exists()


def test_approve_unknown_request_rejected(client, monkeypatch):
    test_client, _ = client
    _capture_user_email(monkeypatch)
    _stub_store(monkeypatch)

    resp = test_client.post(f"/signup/approve?id={'a' * 32}&token=whatever")
    assert resp.status_code == 400


def test_reject_marks_request_and_blocks_later_approval(client, monkeypatch):
    test_client, tmp_path = client
    _capture_user_email(monkeypatch)
    _stub_store(monkeypatch)

    request_id, token = _pending_request(tmp_path)
    resp = test_client.post(f"/signup/reject?id={request_id}&token={token}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "rejected"}

    store_dir = signup_requests.signup_requests_dir(tmp_path)
    assert json.loads((store_dir / f"{request_id}.json").read_text())["status"] == "rejected"

    # A rejected request can no longer be approved with the same token.
    later = test_client.post(f"/signup/approve?id={request_id}&token={token}")
    assert later.status_code == 409


def test_reject_invalid_token_rejected(client, monkeypatch):
    test_client, tmp_path = client
    _stub_store(monkeypatch)

    request_id, _ = _pending_request(tmp_path)
    resp = test_client.post(f"/signup/reject?id={request_id}&token=nope")
    assert resp.status_code == 400


def test_approve_user_email_failure_is_not_swallowed(client, monkeypatch):
    test_client, tmp_path = client
    _stub_store(monkeypatch)

    def boom(user_email, name, login_url):
        raise RuntimeError("SES down")

    monkeypatch.setattr(signup_module, "send_signup_approved_email", boom)

    request_id, token = _pending_request(tmp_path)
    resp = test_client.post(f"/signup/approve?id={request_id}&token={token}")
    assert resp.status_code == 502


def test_get_approve_is_a_safe_confirmation_page(client, monkeypatch):
    """GET (e.g. a clicked/prefetched email link) must not consume the token."""

    test_client, tmp_path = client
    sent = _capture_user_email(monkeypatch)
    _stub_store(monkeypatch)

    request_id, token = _pending_request(tmp_path)
    resp = test_client.get(f"/signup/approve?id={request_id}&token={token}")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    # A confirmation form that POSTs the real action — no side effects yet.
    assert "<form" in resp.text and 'method="post"' in resp.text
    assert "jane@example.com" in resp.text
    # The request is still pending and nothing was provisioned or emailed.
    store_dir = signup_requests.signup_requests_dir(tmp_path)
    assert json.loads((store_dir / f"{request_id}.json").read_text())["status"] == "pending"
    assert not (tmp_path / "accounts" / "jane").exists()
    assert sent == {}

    # The POSTed action still works after the confirmation page.
    posted = test_client.post(f"/signup/approve?id={request_id}&token={token}")
    assert posted.status_code == 200
    assert posted.json()["status"] == "approved"


def test_get_approve_invalid_token_renders_error_page(client, monkeypatch):
    test_client, tmp_path = client
    _stub_store(monkeypatch)

    request_id, _ = _pending_request(tmp_path)
    resp = test_client.get(f"/signup/approve?id={request_id}&token=wrong")
    assert resp.status_code == 400
    assert "text/html" in resp.headers["content-type"]
