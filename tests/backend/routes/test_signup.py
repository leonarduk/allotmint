import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

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


# ---------------------------------------------------------------------------
# Rate limiting (#4364)
# ---------------------------------------------------------------------------


@pytest.fixture
def rate_limited_client(tmp_path, monkeypatch):
    """A test client with per-IP rate limiting on POST /signup/request."""

    accounts_root = tmp_path / "accounts"
    monkeypatch.setattr(
        signup_module,
        "resolve_accounts_root",
        lambda request, allow_missing=False: accounts_root,
    )
    monkeypatch.setenv("SIGNUP_ADMIN_EMAIL", "admin@example.com")

    limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
    router = signup_module.create_router(limiter, "3/minute")

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(
        RateLimitExceeded,
        lambda req, exc: (  # type: ignore[arg-type]
            __import__("starlette.responses").responses.Response(
                content='{"detail":"Rate limit exceeded: 3 per 1 minute"}',
                status_code=429,
                media_type="application/json",
            )
        ),
    )
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(router)
    return TestClient(app), tmp_path


def _capture_for_limited(monkeypatch):
    """Same as _capture_email but works with the rate_limited_client fixture."""

    sent = {}

    def fake_send(admin_email, notification):
        sent["admin_email"] = admin_email
        sent["notification"] = notification

    monkeypatch.setattr(signup_module, "send_signup_admin_email", fake_send)
    return sent


def test_rate_limit_allows_up_to_limit(rate_limited_client, monkeypatch):
    """Requests within the rate limit succeed."""

    test_client, _ = rate_limited_client
    _capture_for_limited(monkeypatch)

    for i in range(3):
        resp = test_client.post(
            "/signup/request",
            json={"name": f"User{i}", "email": f"user{i}@example.com"},
        )
        assert resp.status_code == 200, f"request {i} should succeed"


def test_rate_limit_blocks_after_limit(rate_limited_client, monkeypatch):
    """The fourth request from the same IP is throttled (429)."""

    test_client, _ = rate_limited_client
    _capture_for_limited(monkeypatch)

    for i in range(3):
        resp = test_client.post(
            "/signup/request",
            json={"name": f"User{i}", "email": f"user{i}@example.com"},
        )
        assert resp.status_code == 200, f"request {i} should succeed"

    # Fourth request throttled
    resp = test_client.post(
        "/signup/request",
        json={"name": "Flooder", "email": "flooder@example.com"},
    )
    assert resp.status_code == 429


def test_rate_limited_invalid_payload_still_400(rate_limited_client, monkeypatch):
    """Malformed payloads are rejected with 400 and still consume rate-limit quota.

    slowapi checks rate limits at the middleware layer before the handler runs,
    so even requests that fail validation count. This is acceptable for abuse
    protection: a flooder cannot bypass the rate limit by sending garbage.
    """

    test_client, _ = rate_limited_client
    _capture_for_limited(monkeypatch)

    # Bad payloads consume rate limit quota (slowapi middleware runs first).
    for _ in range(3):
        resp = test_client.post("/signup/request", json={"name": "", "email": "nope"})
        assert resp.status_code == 400

    # Fourth request (even with valid payload) is now throttled.
    resp = test_client.post(
        "/signup/request",
        json={"name": "User", "email": "user@example.com"},
    )
    assert resp.status_code == 429


def test_throttling_response_is_identical_for_all_emails(rate_limited_client, monkeypatch):
    """Rate-limit response must not leak whether an email has an account."""

    test_client, _ = rate_limited_client
    _capture_for_limited(monkeypatch)

    # Burn through the rate limit.
    for i in range(3):
        test_client.post(
            "/signup/request",
            json={"name": f"User{i}", "email": f"user{i}@example.com"},
        )

    # Throttled responses must be identical regardless of the submitted email.
    resp_existing = test_client.post(
        "/signup/request",
        json={"name": "Existing", "email": "alice@example.com"},
    )
    resp_new = test_client.post(
        "/signup/request",
        json={"name": "New", "email": "brandnew@example.com"},
    )

    assert resp_existing.status_code == resp_new.status_code == 429
    assert resp_existing.json() == resp_new.json()


# ---------------------------------------------------------------------------
# Disk bounding (prune stale / cap pending)
# ---------------------------------------------------------------------------


def test_prune_stale_removes_expired_requests(tmp_path):
    """Expired pending requests are removed before persisting a new one."""

    from datetime import datetime, timedelta, timezone

    store_dir = signup_requests.signup_requests_dir(tmp_path)
    now = datetime(2025, 1, 15, tzinfo=timezone.utc)

    # Create a fresh request first (so it survives later prunes).
    fresh_record, _ = signup_requests.create_signup_request(
        "Fresh",
        "fresh@example.com",
        "",
        store_dir,
        now=now,
    )
    # Create a request that expired 1 day ago (created 8 days before now).
    _, _ = signup_requests.create_signup_request(
        "Old",
        "old@example.com",
        "",
        store_dir,
        now=now - timedelta(days=8),  # TTL is 7 days, so expires at now-1day
    )

    assert len(list(store_dir.glob("*.json"))) == 2

    # Persisting a third request triggers prune (now + 1 hour > stale expires).
    signup_requests.create_signup_request(
        "Third",
        "third@example.com",
        "",
        store_dir,
        now=now + timedelta(hours=1),
    )

    files = list(store_dir.glob("*.json"))
    # The expired one should be gone; the fresh one and the new one remain.
    file_ids = {json.loads(f.read_text())["id"] for f in files}
    assert fresh_record.id in file_ids
    assert len(files) == 2


def test_enforce_cap_removes_oldest_when_exceeded(tmp_path):
    """When pending requests exceed the cap, oldest are removed first."""

    from datetime import datetime, timedelta, timezone

    store_dir = signup_requests.signup_requests_dir(tmp_path)
    now = datetime(2025, 1, 15, tzinfo=timezone.utc)

    # Create MAX_PENDING_REQUESTS fresh requests.
    max_pending = signup_requests._MAX_PENDING_REQUESTS
    created = []
    for i in range(max_pending):
        record, _ = signup_requests.create_signup_request(
            f"User{i}",
            f"user{i}@example.com",
            "",
            store_dir,
            now=now + timedelta(seconds=i),
        )
        created.append(record.id)

    assert len(list(store_dir.glob("*.json"))) == max_pending

    # The oldest request should be first in the list.
    oldest_id = created[0]

    # Persisting one more triggers cap enforcement.
    new_record, _ = signup_requests.create_signup_request(
        "New",
        "new@example.com",
        "",
        store_dir,
        now=now + timedelta(hours=1),
    )

    files = list(store_dir.glob("*.json"))
    assert len(files) == max_pending  # capped back to max

    file_ids = {json.loads(f.read_text())["id"] for f in files}
    # Oldest was evicted.
    assert oldest_id not in file_ids
    # Newest is present.
    assert new_record.id in file_ids
    # All but the oldest remain.
    for rid in created[1:]:
        assert rid in file_ids
