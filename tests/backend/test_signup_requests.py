import json
from datetime import datetime, timedelta, timezone
import time

from pathlib import Path
import pytest

from concurrent.futures import ThreadPoolExecutor

from backend.common import signup_requests


def test_normalise_payload_trims_and_lowercases_email():
    name, email, note = signup_requests.normalise_payload(
        {"name": "  Jane Doe ", "email": "  Jane@Example.COM ", "note": "  hi  "}
    )
    assert name == "Jane Doe"
    assert email == "jane@example.com"
    assert note == "hi"


def test_normalise_payload_allows_missing_note():
    name, email, note = signup_requests.normalise_payload({"name": "Jane", "email": "jane@example.com"})
    assert (name, email, note) == ("Jane", "jane@example.com", "")


@pytest.mark.parametrize(
    "payload",
    [
        "not a dict",
        {"name": "", "email": "jane@example.com"},
        {"name": "Jane", "email": "not-an-email"},
        {"name": "Jane", "email": "missing-at.example.com"},
        {"name": "Jane", "email": "two@at@example.com"},
        {"name": "Jane", "email": "jane@example..com"},
        {"name": "Jane", "email": "jane@.example.com"},
        {"name": "Jane", "email": "jane@example."},
        {"name": "Jane", "email": "jane@nodot"},
        {"name": "Jane", "email": "jane doe@example.com"},
        {"name": "Jane", "email": ""},
        {"name": "x" * 201, "email": "jane@example.com"},
        {"name": "Jane", "email": "jane@example.com", "note": "x" * 2001},
    ],
)
def test_normalise_payload_rejects_invalid(payload):
    with pytest.raises(signup_requests.SignupValidationError):
        signup_requests.normalise_payload(payload)


def test_email_validation_is_linear_on_adversarial_input():
    """A ReDoS-style payload must be rejected quickly, not backtrack.

    The previous regex (``[^@\\s]+@[^@\\s]+\\.[^@\\s]+``) was polynomial on
    strings like ``!@!.!.!.!.``; the string-based check is linear.
    """
    adversarial = "!@" + "!." * 8000
    with pytest.raises(signup_requests.SignupValidationError):
        signup_requests.normalise_payload({"name": "Jane", "email": adversarial})


def test_create_signup_request_persists_record(tmp_path):
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    store = signup_requests.signup_requests_dir(tmp_path)

    record, token = signup_requests.create_signup_request("Jane", "jane@example.com", "hello", store, now=now)

    path = store / f"{record.id}.json"
    assert path.exists()
    saved = json.loads(path.read_text())
    assert saved["email"] == "jane@example.com"
    assert saved["status"] == "pending"
    assert saved["created_at"] == now.isoformat()
    # Expiry is in the future relative to creation.
    assert saved["expires_at"] > saved["created_at"]


def test_create_signup_request_stores_only_token_hash(tmp_path):
    store = signup_requests.signup_requests_dir(tmp_path)
    record, token = signup_requests.create_signup_request("Jane", "jane@example.com", "", store)

    raw = (store / f"{record.id}.json").read_text()
    # Plaintext token must never be persisted; only its hash.
    assert token not in raw
    assert record.token_sha256 == signup_requests.hash_token(token)
    assert "token_sha256" in json.loads(raw)


def test_create_signup_request_tokens_are_unique_and_high_entropy(tmp_path):
    store = signup_requests.signup_requests_dir(tmp_path)
    _, token_a = signup_requests.create_signup_request("A", "a@example.com", "", store)
    _, token_b = signup_requests.create_signup_request("B", "b@example.com", "", store)

    assert token_a != token_b
    # secrets.token_urlsafe(32) yields ~43 url-safe characters.
    assert len(token_a) >= 32


def test_load_request_round_trips(tmp_path):
    store = signup_requests.signup_requests_dir(tmp_path)
    record, _ = signup_requests.create_signup_request("Jane", "jane@example.com", "", store)

    loaded = signup_requests.load_request(record.id, store)
    assert loaded == record


def test_load_request_rejects_traversal_ids(tmp_path):
    store = signup_requests.signup_requests_dir(tmp_path)
    assert signup_requests.load_request("../secret", store) is None
    assert signup_requests.load_request("not-hex!!", store) is None
    assert signup_requests.load_request("", store) is None


def test_consume_request_marks_status_and_is_single_use(tmp_path):
    store = signup_requests.signup_requests_dir(tmp_path)
    record, token = signup_requests.create_signup_request("Jane", "jane@example.com", "", store)

    updated = signup_requests.consume_request(record.id, token, store, new_status="approved")
    assert updated.status == "approved"
    saved = json.loads((store / f"{record.id}.json").read_text())
    assert saved["status"] == "approved"

    # Re-using the same token is rejected — single-use.
    with pytest.raises(signup_requests.RequestAlreadyProcessed):
        signup_requests.consume_request(record.id, token, store, new_status="approved")


def test_consume_request_rejects_bad_token(tmp_path):
    store = signup_requests.signup_requests_dir(tmp_path)
    record, _ = signup_requests.create_signup_request("Jane", "jane@example.com", "", store)

    with pytest.raises(signup_requests.TokenInvalid):
        signup_requests.consume_request(record.id, "wrong-token", store, new_status="approved")
    # A failed attempt must not flip the status.
    assert json.loads((store / f"{record.id}.json").read_text())["status"] == "pending"


def test_consume_request_rejects_unknown_id(tmp_path):
    store = signup_requests.signup_requests_dir(tmp_path)
    with pytest.raises(signup_requests.RequestNotFound):
        signup_requests.consume_request("a" * 32, "tok", store, new_status="approved")


def test_consume_request_rejects_expired_token(tmp_path):
    store = signup_requests.signup_requests_dir(tmp_path)
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    record, token = signup_requests.create_signup_request("Jane", "jane@example.com", "", store, now=created)

    later = created + timedelta(days=365)
    with pytest.raises(signup_requests.RequestExpired):
        signup_requests.consume_request(record.id, token, store, new_status="approved", now=later)


def test_validate_request_does_not_mutate(tmp_path):
    store = signup_requests.signup_requests_dir(tmp_path)
    record, token = signup_requests.create_signup_request("Jane", "jane@example.com", "", store)

    validated = signup_requests.validate_request(record.id, token, store)
    assert validated.status == "pending"
    # No write occurred, so the token can still be consumed afterwards.
    assert json.loads((store / f"{record.id}.json").read_text())["status"] == "pending"
    consumed = signup_requests.consume_request(record.id, token, store, new_status="approved")
    assert consumed.status == "approved"

def test_enforce_cap_race_condition(tmp_path, monkeypatch):
    store = signup_requests.signup_requests_dir(tmp_path)
    store.mkdir(parents=True, exist_ok=True)

    # Seed directory with too many pending files so _enforce_cap MUST run
    for i in range(signup_requests._MAX_PENDING_REQUESTS + 5):
        (store / f"req_{i}.json").write_text(json.dumps({
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat()
        }))

    # Monkeypatch Path.glob to force overlap inside _enforce_cap
    real_glob = Path.glob

    def slow_glob(self, pattern):
        time.sleep(0.01)  # force threads to overlap
        return real_glob(self, pattern)

    monkeypatch.setattr(Path, "glob", slow_glob)

    # Run TWO concurrent create_signup_request calls
    # This triggers _persist() → _enforce_cap() → write new file
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = [
            ex.submit(
                signup_requests.create_signup_request,
                "A", "a@example.com", "", store
            )
            for _ in range(2)
        ]
        for f in futures:
            f.result()

    # Now check that the cap was respected
    files = list(store.glob("*.json"))
    assert len(files) <= signup_requests._MAX_PENDING_REQUESTS


def test_enforce_cap_lock_acquisition_failure(tmp_path, monkeypatch):
    store = signup_requests.signup_requests_dir(tmp_path)
    store.mkdir(parents=True, exist_ok=True)

    # Create at least one pending request to trigger lock acquisition
    (store / "req_1.json").write_text(json.dumps({
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }))

    # Mock the lock to fail acquisition
    class FailingLock:
        def __init__(self, path):
            self.path = path
            self.acquired = False

        def acquire(self, timeout=None):
            return False  # Always fail to acquire

        def release(self):
            pass

    monkeypatch.setattr("backend.common.signup_requests.InterProcessLock", FailingLock)

    # Should raise HTTPException(503) when lock cannot be acquired
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        signup_requests._enforce_cap(store, signup_requests._MAX_PENDING_REQUESTS)

    assert exc_info.value.status_code == 503


def test_enforce_cap_lock_file_cleanup(tmp_path):
    store = signup_requests.signup_requests_dir(tmp_path)
    store.mkdir(parents=True, exist_ok=True)

    # Seed with files that will trigger cap enforcement
    for i in range(signup_requests._MAX_PENDING_REQUESTS + 5):
        (store / f"req_{i}.json").write_text(json.dumps({
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat()
        }))

    # Run _enforce_cap
    signup_requests._enforce_cap(store, signup_requests._MAX_PENDING_REQUESTS)

    # Lock file should be cleaned up after release
    lock_file = signup_requests._lock_path(store)
    assert not lock_file.exists(), "Lock file should be cleaned up after _enforce_cap completes"
