import json
from datetime import datetime, timezone

import pytest

from backend.common import signup_requests


def test_normalise_payload_trims_and_lowercases_email():
    name, email, note = signup_requests.normalise_payload(
        {"name": "  Jane Doe ", "email": "  Jane@Example.COM ", "note": "  hi  "}
    )
    assert name == "Jane Doe"
    assert email == "jane@example.com"
    assert note == "hi"


def test_normalise_payload_allows_missing_note():
    name, email, note = signup_requests.normalise_payload(
        {"name": "Jane", "email": "jane@example.com"}
    )
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

    record, token = signup_requests.create_signup_request(
        "Jane", "jane@example.com", "hello", store, now=now
    )

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
