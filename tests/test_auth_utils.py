import json

import pytest
from fastapi import HTTPException

from backend import auth
from backend.config import config

ORIGINAL_VERIFY = auth.verify_google_token


def test_create_and_decode_token_round_trip():
    token = auth.create_access_token("user@example.com")
    assert auth.decode_token(token) == "user@example.com"


def test_decode_token_invalid_returns_none():
    assert auth.decode_token("not-a-token") is None


def test_verify_google_token_rejects_when_no_allowed_emails(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "verify_google_token", ORIGINAL_VERIFY)
    root = tmp_path / "accounts"
    root.mkdir()
    monkeypatch.setattr(config, "accounts_root", root)
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "google_client_id", "client")

    def fake_verify(token, request, audience):
        return {"email": "user@example.com", "email_verified": True}

    monkeypatch.setattr("backend.auth.id_token.verify_oauth2_token", fake_verify)

    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("dummy")
    assert exc.value.status_code == 403


def test_verify_google_token_rejects_unverified_email(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "verify_google_token", ORIGINAL_VERIFY)
    root = tmp_path / "accounts"
    root.mkdir()
    monkeypatch.setattr(config, "accounts_root", root)
    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "google_client_id", "client")

    def fake_verify(token, request, audience):
        return {"email": "user@example.com", "email_verified": False}

    monkeypatch.setattr("backend.auth.id_token.verify_oauth2_token", fake_verify)

    with pytest.raises(HTTPException) as exc:
        auth.verify_google_token("dummy")
    assert exc.value.status_code == 401


def test_emails_for_person_meta_includes_owner_email_and_viewers():
    from backend.common.account_models import PersonMetadata

    person = PersonMetadata(
        owner="alice",
        email="Alice@Example.com",
        viewers=["Bob@Example.com", "carol@example.com", "  "],
    )

    assert auth._emails_for_person_meta(person) == {
        "alice@example.com",
        "bob@example.com",
        "carol@example.com",
    }


def test_emails_for_person_meta_handles_none():
    assert auth._emails_for_person_meta(None) == set()


def test_allowed_emails_includes_viewer_emails(monkeypatch, tmp_path):
    """A viewer granted access via person.json must be able to authenticate.

    Regression test for #5215: ``ensure_owner_access``/``identity_can_access_owner``
    already grant a listed viewer access to an owner's data, but
    ``_allowed_emails`` (consulted earlier, at identity-resolution time) only
    looked at each owner's own ``email`` field -- so a legitimate viewer was
    rejected with a 403 "Unauthorized email" before that per-owner check was
    ever reached.
    """

    monkeypatch.setattr(config, "app_env", "local")
    root = tmp_path / "accounts"
    owner_dir = root / "alice"
    owner_dir.mkdir(parents=True)
    person = {"owner": "alice", "email": "alice@example.com", "viewers": ["bob@example.com"]}
    (owner_dir / "person.json").write_text(json.dumps(person), encoding="utf-8")
    monkeypatch.setattr(config, "accounts_root", root)

    assert auth._allowed_emails() == {"alice@example.com", "bob@example.com"}
