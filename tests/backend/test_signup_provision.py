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


def test_provision_owner_reuses_slug_for_mixed_case_email(tmp_path):
    """A re-request with different email casing must not split into a new slug."""

    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir()

    first = signup_provision.provision_owner(_record("jane@example.com"), accounts_root)
    # record.email is normalised at creation, but provisioning must also be
    # case-insensitive defensively.
    second = signup_provision.provision_owner(_record("JANE@example.com"), accounts_root)

    assert first == second == "jane"


def test_provision_owner_preserves_existing_full_name(tmp_path):
    accounts_root = tmp_path / "accounts"
    (accounts_root / "jane").mkdir(parents=True)
    (accounts_root / "jane" / "person.json").write_text(
        json.dumps({"owner": "jane", "email": "jane@example.com", "full_name": "Existing Name"})
    )

    signup_provision.provision_owner(_record("jane@example.com", name="New Name"), accounts_root)

    person = json.loads((accounts_root / "jane" / "person.json").read_text())
    assert person["full_name"] == "Existing Name"


def test_provision_owner_skips_slug_with_corrupted_person_json(tmp_path):
    """A corrupt person.json must not be treated as this email's account."""

    accounts_root = tmp_path / "accounts"
    (accounts_root / "jane").mkdir(parents=True)
    (accounts_root / "jane" / "person.json").write_text("{ not json")

    owner = signup_provision.provision_owner(_record("jane@example.com"), accounts_root)

    # The corrupt directory is not reused; a fresh slug is allocated.
    assert owner == "jane-2"
    # The corrupt file is left untouched.
    assert (accounts_root / "jane" / "person.json").read_text() == "{ not json"


def test_resolve_owner_slug_stamps_identity_immediately_after_mkdir(tmp_path):
    """Regression test for #4402.

    A concurrent approval for the *same* email that loses the ``mkdir`` race
    must see the winner's identity (email + full_name) via
    ``_read_person_email`` right away, not after the caller gets around to
    calling ``_write_person_identity``. This simulates the losing side of that
    race by calling ``_resolve_owner_slug`` directly (not through
    ``provision_owner``, which would also write the email but only after
    returning).
    """

    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir()

    winner = signup_provision._resolve_owner_slug(
        "jane@example.com", accounts_root, "Jane Doe"
    )
    assert winner == "jane"

    # The winner's person.json must carry the complete identity immediately.
    person = json.loads((accounts_root / "jane" / "person.json").read_text())
    assert person["email"] == "jane@example.com"
    assert person["full_name"] == "Jane Doe"

    # The loser of the mkdir race hits FileExistsError on "jane" immediately
    # after the winner's mkdir succeeds. Without the fix, person.json is not
    # written yet at this point, so the loser would fail to recognise the
    # slug as already claimed by this email and allocate "jane-2" instead.
    loser = signup_provision._resolve_owner_slug("jane@example.com", accounts_root)
    assert loser == "jane"
    assert sorted(p.name for p in accounts_root.iterdir()) == ["jane"]


def test_resolve_owner_slug_cleans_up_on_write_failure(tmp_path, monkeypatch):
    """If the identity write fails after mkdir, the orphan directory is removed."""

    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir()

    def _failing_write(*_args, **_kwargs):
        raise OSError("simulated disk full")

    monkeypatch.setattr(signup_provision, "_write_person_identity", _failing_write)

    with pytest.raises(OSError, match="simulated disk full"):
        signup_provision._resolve_owner_slug("jane@example.com", accounts_root, "Jane Doe")

    # The directory created by mkdir must be cleaned up.
    assert not (accounts_root / "jane").exists()


def test_resolve_owner_slug_raises_when_exhausted(tmp_path, monkeypatch):
    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir()
    monkeypatch.setattr(signup_provision, "_MAX_SLUG_CANDIDATES", 2)

    # Occupy both candidate slugs with a different email so none can be reused.
    for name in ("jane", "jane-2"):
        (accounts_root / name).mkdir()
        (accounts_root / name / "person.json").write_text(
            json.dumps({"email": "other@example.com"})
        )

    with pytest.raises(RuntimeError):
        signup_provision.provision_owner(_record("jane@example.com"), accounts_root)
