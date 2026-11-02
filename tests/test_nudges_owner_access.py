"""``/nudges`` only lets a caller act on, or see, nudges for users they may act for (#11353).

A nudge's ``user`` is an owner id or the signed-in identity itself.
``POST /nudges/subscribe`` and ``POST /nudges/snooze`` run the real
``ensure_owner_access`` against real ``person.json`` files, and
``GET /nudges/`` returns only the nudges whose user passes the same check
(plus nudges with no user), so every id the notifications drawer offers is one
it may act on. Auth-enabled tests sign in through the real ``POST /token``
(``user@example.com`` via the conftest Google stub).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend import nudges as nudge_utils
from backend.app import create_app
from backend.config import config

_ME = "user@example.com"
# alice: the signed-in user's own owner (by email); carol: lists them as a
# viewer; bob: no relation.
_PEOPLE = {
    "alice": {"owner": "alice", "email": _ME},
    "bob": {"owner": "bob", "email": "bob@example.com"},
    "carol": {"owner": "carol", "email": "carol@example.com", "viewers": [_ME]},
}
_DEMO_OWNER = "alice"
# The recent-nudge feed: ``id`` is the user the nudge was sent for.
_FEED = [
    {"id": "alice", "message": "Reminder for alice", "timestamp": "2026-11-01T00:00:00+00:00"},
    {"id": "bob", "message": "Reminder for bob", "timestamp": "2026-11-01T00:00:00+00:00"},
    {"id": "carol", "message": "Reminder for carol", "timestamp": "2026-11-01T00:00:00+00:00"},
    {"id": _ME, "message": "Reminder for me", "timestamp": "2026-11-01T00:00:00+00:00"},
    {"id": "stranger@example.com", "message": "Reminder for a stranger", "timestamp": "2026-11-01T00:00:00+00:00"},
    {"message": "Reminder with no user", "timestamp": "2026-11-01T00:00:00+00:00"},
]
_ALL_IDS = ["alice", "bob", "carol", _ME, "stranger@example.com", None]
_MY_IDS = ["alice", "carol", _ME, None]


@pytest.fixture
def writes(monkeypatch):
    """Stub nudge storage: serve ``_FEED`` and record each subscribe/snooze."""
    recorded: list = []
    monkeypatch.setattr(nudge_utils, "get_recent_nudges", lambda limit=50: list(_FEED))
    monkeypatch.setattr(nudge_utils, "set_user_nudge", lambda user, *a: recorded.append(("subscribe", user)))
    monkeypatch.setattr(nudge_utils, "snooze_user", lambda user, days: recorded.append(("snooze", user)))
    return recorded


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    # CI sets DATA_BUCKET, which would make load_person_meta read S3 instead of these files.
    monkeypatch.delenv("DATA_BUCKET", raising=False)
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    for owner, person in _PEOPLE.items():
        (tmp_path / owner).mkdir()
        (tmp_path / owner / "person.json").write_text(json.dumps(person))
        (tmp_path / owner / "isa.json").write_text(
            json.dumps({"owner": owner, "account_type": "isa", "currency": "GBP", "holdings": []})
        )
    return tmp_path


def _signed_in_client(monkeypatch) -> TestClient:
    """Auth enabled, signed in through the real ``/token`` endpoint as ``user@example.com``."""
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _feed_ids(client) -> list:
    resp = client.get("/nudges/")
    assert resp.status_code == 200, resp.text
    return [n.get("id") for n in resp.json()]


def _act(client, action, user):
    if action == "subscribe":
        return client.post("/nudges/subscribe", json={"user": user, "frequency": 3})
    return client.post("/nudges/snooze", json={"user": user, "days": 30})


@pytest.mark.parametrize("action", ["subscribe", "snooze"])
@pytest.mark.parametrize("user", ["bob", "BOB", "stranger@example.com"])
def test_signed_in_caller_cannot_act_for_another_user(accounts, writes, monkeypatch, action, user):
    client = _signed_in_client(monkeypatch)

    resp = _act(client, action, user)

    assert resp.status_code == 403, resp.text
    assert resp.json() == {"detail": "Not authorized for this owner"}
    assert writes == []


@pytest.mark.parametrize("action", ["subscribe", "snooze"])
@pytest.mark.parametrize("user", ["alice", "carol", _ME, "USER@example.com"])
def test_signed_in_caller_acts_for_self_owned_and_viewed_owners(accounts, writes, monkeypatch, action, user):
    client = _signed_in_client(monkeypatch)

    resp = _act(client, action, user)

    assert resp.status_code == 200, resp.text
    assert writes == [(action, user)]


def test_signed_in_feed_only_shows_nudges_the_caller_may_act_on(accounts, writes, monkeypatch):
    client = _signed_in_client(monkeypatch)

    assert _feed_ids(client) == _MY_IDS


def test_drawer_flow_every_feed_id_can_be_snoozed_and_rescheduled(accounts, writes, monkeypatch):
    """The notifications drawer snoozes/subscribes with each nudge's ``id``; none may be refused."""
    client = _signed_in_client(monkeypatch)

    for user in _feed_ids(client):
        if user is None:
            continue
        assert _act(client, "snooze", user).status_code == 200, user
        assert _act(client, "subscribe", user).status_code == 200, user


def test_anonymous_request_is_401_with_auth_enabled(accounts, writes, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())

    assert client.get("/nudges/").status_code == 401
    assert _act(client, "snooze", "alice").status_code == 401
    assert writes == []


def test_auth_disabled_with_flag_off_is_unchanged(accounts, writes, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "enforce_owner_access", False)
    monkeypatch.setattr(config, "local_login_email", None, raising=False)
    client = TestClient(create_app())

    assert _feed_ids(client) == _ALL_IDS
    assert _act(client, "snooze", "bob").status_code == 200
    assert _act(client, "subscribe", "stranger@example.com").status_code == 200
    assert writes == [("snooze", "bob"), ("subscribe", "stranger@example.com")]


def test_auth_disabled_ignores_an_unreadable_token_as_before(accounts, writes, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "enforce_owner_access", False)
    client = TestClient(create_app())
    client.headers.update({"Authorization": "Bearer not-a-jwt"})

    assert _feed_ids(client) == _ALL_IDS
    assert _act(client, "snooze", "bob").status_code == 200


def test_enforce_owner_access_flag_checks_the_request_identity(accounts, writes, monkeypatch):
    """#11350's flag: ``disable_auth`` plus ``ENFORCE_OWNER_ACCESS`` checks the gateway identity."""
    monkeypatch.setattr(config, "disable_auth", True)
    client = TestClient(create_app())
    monkeypatch.setattr(config, "enforce_owner_access", True)
    monkeypatch.setattr(config, "local_login_email", _ME, raising=False)

    assert _feed_ids(client) == _MY_IDS
    assert _act(client, "snooze", "carol").status_code == 200
    assert _act(client, "snooze", _ME).status_code == 200
    assert _act(client, "snooze", "bob").status_code == 403
    assert _act(client, "subscribe", "stranger@example.com").status_code == 403
    assert writes == [("snooze", "carol"), ("snooze", _ME)]


def test_enforce_owner_access_flag_with_no_identity_denies_everything(accounts, writes, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", True)
    client = TestClient(create_app())
    monkeypatch.setattr(config, "enforce_owner_access", True)
    monkeypatch.setattr(config, "local_login_email", None, raising=False)

    assert _feed_ids(client) == [None]
    assert _act(client, "snooze", "alice").status_code == 403
    assert writes == []


@pytest.mark.parametrize("disable_auth", [True, False])
def test_demo_token_sees_only_the_demo_owner(accounts, writes, monkeypatch, disable_auth):
    monkeypatch.setattr(config, "disable_auth", disable_auth)
    client = TestClient(create_app())
    # Patched after create_app(), whose config reload would otherwise reset them.
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", _DEMO_OWNER, raising=False)
    client.headers.update({"Authorization": f"Bearer {auth.create_demo_access_token(_DEMO_OWNER)}"})

    assert _feed_ids(client) == [_DEMO_OWNER, None]
    # Demo tokens are read-only (#7407): no write reaches the store.
    assert _act(client, "snooze", "bob").status_code == 403
    assert _act(client, "snooze", _DEMO_OWNER).status_code == 403
    assert writes == []
