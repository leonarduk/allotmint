import json

import pytest

from backend.common import signup_provision
from backend.common.signup_requests import SignupRequest


def _record(email: str, name: str = "Jane Doe") -> SignupRequest:
    return SignupRequest(
        id="a" * 32,
        name=name,
        email=email,
        note="",
        status="pending",
        created_at="2026-06-15T12:00:00+00:00",
        expires_at="2026-06-22T12:00:00+00:00",
        token_sha256="deadbeef",
    )


@pytest.mark.parametrize(
    "email,expected",
    [
        ("jane.doe@example.com", "jane-doe"),
        ("JANE@example.com", "jane"),
        ("a+b_c@example.com", "a-b-c"),
        ("@example.com", "user"),
    ],
)
def test_derive_owner_slug(email, expected):
    assert signup_provision.derive_owner_slug(email) == expected


def test_provision_owner_scaffolds_and_writes_email(tmp_path):
    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir()

    owner = signup_provision.provision_owner(_record("jane@example.com"), accounts_root)

    assert owner == "jane"
    person = json.loads((accounts_root / "jane" / "person.json").read_text())
    assert person["email"] == "jane@example.com"
    assert person["full_name"] == "Jane Doe"
    # Scaffold also produced the standard companion files.
    assert (accounts_root / "jane" / "settings.json").exists()
    assert (accounts_root / "jane" / "approvals.json").exists()


def test_provision_owner_is_idempotent_for_same_email(tmp_path):
    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir()
    record = _record("jane@example.com")

    first = signup_provision.provision_owner(record, accounts_root)
    second = signup_provision.provision_owner(record, accounts_root)

    assert first == second == "jane"
    assert sorted(p.name for p in accounts_root.iterdir()) == ["jane"]


def test_provision_owner_avoids_clobbering_a_different_email(tmp_path):
    accounts_root = tmp_path / "accounts"
    (accounts_root / "jane").mkdir(parents=True)
    (accounts_root / "jane" / "person.json").write_text(
        json.dumps({"owner": "jane", "email": "someone-else@example.com"})
    )

    owner = signup_provision.provision_owner(_record("jane@example.com"), accounts_root)

    assert owner == "jane-2"
    # The pre-existing account is untouched.
    existing = json.loads((accounts_root / "jane" / "person.json").read_text())
    assert existing["email"] == "someone-else@example.com"


def test_provision_owner_calls_store_ensure_owner(tmp_path):
    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir()
    calls = []

    class FakeStore:
        def ensure_owner(self, owner):
            calls.append(owner)

    signup_provision.provision_owner(_record("jane@example.com"), accounts_root, store=FakeStore())
    assert calls == ["jane"]
