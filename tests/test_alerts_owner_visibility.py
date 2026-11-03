"""``GET /alerts/`` hides alerts about owners the caller may not see (#11359).

Owner-specific alerts (cost-basis moves, trade imports, nudges, drift) carry
``owner`` when they are published, and the feed keeps only those whose owner
the caller may see by the ``/owners`` rule (``list_plots(current_user=...)``),
plus alerts with no owner: global price-trigger and agent alerts, and legacy
alerts stored before owners were recorded.

Alerts are published through the real publishers into the real (test-isolated)
alert history. Auth-enabled tests sign in through the real ``POST /token``
(``user@example.com`` via the conftest Google stub) against real
``person.json`` files.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend import nudges as nudge_utils
from backend.alerts import evaluate_drift
from backend.app import create_app
from backend.common import alerts as common_alerts
from backend.common import portfolio_utils
from backend.config import config
from backend.tasks import trades

_ME = "user@example.com"
# alice: the signed-in user's own owner (by email); carol: lists them as a
# viewer; bob: no relation.
_PEOPLE = {
    "alice": {"owner": "alice", "email": _ME},
    "bob": {"owner": "bob", "email": "bob@example.com"},
    "carol": {"owner": "carol", "email": "carol@example.com", "viewers": [_ME]},
}
_DEMO_OWNER = "alice"
_GLOBAL = ["Price trigger: AAA.L crossed 100", "BUY AAA.L - RSI oversold", "Imported 3 trades for bob (legacy)"]


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    # CI sets DATA_BUCKET, which would make load_person_meta read S3 instead of these files.
    monkeypatch.delenv("DATA_BUCKET", raising=False)
    monkeypatch.setattr(config, "accounts_root", tmp_path / "accounts")
    for owner, person in _PEOPLE.items():
        owner_dir = tmp_path / "accounts" / owner
        owner_dir.mkdir(parents=True)
        (owner_dir / "person.json").write_text(json.dumps(person))
        (owner_dir / "isa.json").write_text(
            json.dumps({"owner": owner, "account_type": "isa", "currency": "GBP", "holdings": []})
        )
    return tmp_path


@pytest.fixture
def published(accounts, monkeypatch):
    """Publish owner-specific and global alerts through the real publishers."""
    monkeypatch.setattr(common_alerts.config, "sns_topic_arn", None)
    common_alerts.clear_state()

    # Cost-basis moves: alice and bob hold the same ticker with the same move.
    holding = {"ticker": "AAA", "units": 1, "cost_gbp": 100}
    portfolios = [{"owner": o, "accounts": [{"holdings": [dict(holding)]}]} for o in ("alice", "bob")]
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {"AAA.L": {"last_price": 120.0}})
    monkeypatch.setattr(portfolio_utils, "list_portfolios", lambda: portfolios)
    portfolio_utils.check_price_alerts(threshold_pct=0.05)

    # Trade imports for carol and bob.
    monkeypatch.setattr(trades.AlpacaAPI, "recent_trades", lambda self, since: [{"ticker": "X", "units": "1"}])
    monkeypatch.setattr(trades, "persist_trades", lambda owner, rows: len(rows))
    for owner in ("carol", "bob"):
        trades.lambda_handler({"owner": owner}, None)

    # Drift alerts for alice and bob.
    evaluate_drift("alice", 100.0, 150.0, threshold=0.1)
    evaluate_drift("bob", 100.0, 150.0, threshold=0.1)

    # Global alerts: a price trigger and an agent signal carry no owner, and
    # neither does a legacy alert stored before owners were recorded.
    common_alerts.publish_alert({"ticker": "AAA.L", "user": "someone", "message": _GLOBAL[0]})
    common_alerts.publish_alert({"message": _GLOBAL[1]})
    common_alerts.publish_alert({"ticker": "IMPORT", "change_pct": 0.0, "message": _GLOBAL[2]})
    yield
    common_alerts.clear_state()


def _signed_in_client(monkeypatch) -> TestClient:
    """Auth enabled, signed in through the real ``/token`` endpoint as ``user@example.com``."""
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _feed(client) -> list:
    resp = client.get("/alerts/")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _owners(feed) -> set:
    return {a.get("owner") for a in feed}


def _assert_globals_kept(feed) -> None:
    messages = [a["message"] for a in feed]
    for message in _GLOBAL:
        assert message in messages


def test_publishers_tag_owner_specific_alerts(published):
    stored = common_alerts.get_recent_alerts()
    by_owner = {}
    for alert in stored:
        by_owner.setdefault(alert.get("owner"), []).append(alert["message"])
    # The same cost-basis message for two owners is stored once per owner.
    assert "AAA.L change 20.0% vs cost basis" in by_owner["alice"]
    assert "AAA.L change 20.0% vs cost basis" in by_owner["bob"]
    assert "Imported 1 trades for carol" in by_owner["carol"]
    assert "Imported 1 trades for bob" in by_owner["bob"]
    assert any("drift" in m for m in by_owner["alice"])
    assert sorted(by_owner[None]) == sorted(_GLOBAL)


def test_send_due_nudges_tags_the_nudge_user(monkeypatch):
    published = []
    monkeypatch.setattr(nudge_utils, "publish_alert", published.append)
    monkeypatch.setattr(nudge_utils, "iter_due_users", lambda now: iter(["bob"]))
    monkeypatch.setattr(nudge_utils, "_build_nudge_message", lambda user: f"Reminder for {user}")
    monkeypatch.setattr(nudge_utils, "_save_state", lambda: None)
    monkeypatch.setattr(nudge_utils.config, "telegram_bot_token", None, raising=False)
    monkeypatch.setitem(nudge_utils._SUBSCRIPTIONS, "bob", {"frequency": 7})
    monkeypatch.setattr(nudge_utils, "_RECENT_NUDGES", [])

    nudge_utils.send_due_nudges()

    assert published == [{"ticker": "NUDGE", "user": "bob", "owner": "bob", "message": "Reminder for bob"}]


def test_signed_in_user_sees_own_and_viewed_owners_plus_global(published, monkeypatch):
    client = _signed_in_client(monkeypatch)

    feed = _feed(client)

    assert _owners(feed) == {"alice", "carol", None}
    assert "bob" not in json.dumps([a for a in feed if a["message"] not in _GLOBAL])
    _assert_globals_kept(feed)


def test_anonymous_request_is_401_with_auth_enabled(published, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", False)
    client = TestClient(create_app())

    assert client.get("/alerts/").status_code == 401


def test_auth_disabled_with_flag_off_is_unchanged(published, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "enforce_owner_access", False)
    monkeypatch.setattr(config, "local_login_email", None, raising=False)
    client = TestClient(create_app())

    feed = _feed(client)

    assert feed == common_alerts.get_recent_alerts()
    assert _owners(feed) == {"alice", "bob", "carol", None}


def test_auth_disabled_ignores_an_unreadable_token_as_before(published, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", True)
    monkeypatch.setattr(config, "enforce_owner_access", False)
    client = TestClient(create_app())
    client.headers.update({"Authorization": "Bearer not-a-jwt"})

    assert _owners(_feed(client)) == {"alice", "bob", "carol", None}


def test_enforce_owner_access_flag_filters_by_request_identity(published, monkeypatch):
    """#11350's flag: ``disable_auth`` plus ``ENFORCE_OWNER_ACCESS`` filters by the gateway identity."""
    monkeypatch.setattr(config, "disable_auth", True)
    client = TestClient(create_app())
    monkeypatch.setattr(config, "enforce_owner_access", True)
    monkeypatch.setattr(config, "local_login_email", _ME, raising=False)

    feed = _feed(client)

    assert _owners(feed) == {"alice", "carol", None}
    _assert_globals_kept(feed)


def test_enforce_owner_access_flag_with_no_identity_shows_only_global(published, monkeypatch):
    monkeypatch.setattr(config, "disable_auth", True)
    client = TestClient(create_app())
    monkeypatch.setattr(config, "enforce_owner_access", True)
    monkeypatch.setattr(config, "local_login_email", None, raising=False)

    feed = _feed(client)

    assert _owners(feed) == {None}
    _assert_globals_kept(feed)


@pytest.mark.parametrize("disable_auth", [True, False])
def test_demo_token_sees_only_the_demo_owner(published, monkeypatch, disable_auth):
    monkeypatch.setattr(config, "disable_auth", disable_auth)
    client = TestClient(create_app())
    # Patched after create_app(), whose config reload would otherwise reset them.
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", _DEMO_OWNER, raising=False)
    client.headers.update({"Authorization": f"Bearer {auth.create_demo_access_token(_DEMO_OWNER)}"})

    feed = _feed(client)

    assert _owners(feed) == {_DEMO_OWNER, None}
    _assert_globals_kept(feed)


def test_alert_owner_is_matched_case_insensitively(published, monkeypatch):
    common_alerts.publish_alert({"ticker": "IMPORT", "owner": "CAROL", "message": "Imported 9 trades for CAROL"})
    common_alerts.publish_alert({"ticker": "IMPORT", "owner": "BOB", "message": "Imported 9 trades for BOB"})
    client = _signed_in_client(monkeypatch)

    messages = [a["message"] for a in _feed(client)]

    assert "Imported 9 trades for CAROL" in messages
    assert "Imported 9 trades for BOB" not in messages
