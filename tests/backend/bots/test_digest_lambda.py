"""Bots digest Lambda (#10485): due-day logic, delivery and immediate alerts. Synthetic data only."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytest

from backend.bots import digest_delivery, digest_store
from backend.bots.digest_models import BotDescriptor, BotRunRecord, DigestItem, Severity
from backend.lambda_api import bots_digest as lam

MONDAY = datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc)
TUESDAY = datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc)
BOTS = [BotDescriptor(id="guardian", name="Allowance guardian", scope="owner")]


class FakeSource:
    def __init__(self, items: List[DigestItem]):
        self._record = BotRunRecord(bot_id="guardian", status="ok", started_at=MONDAY, digest_items=items)

    def bots(self) -> List[BotDescriptor]:
        return BOTS

    def latest_run(self, bot_id: str) -> Optional[BotRunRecord]:
        return self._record


def _item(owner="alex"):
    return DigestItem(
        id="sept",
        bot="guardian",
        owner=owner,
        severity=Severity.HIGH,
        title="September contribution of £500 not received",
        action_required=True,
        created=MONDAY,
        dedupe_key="guardian:sept",
    )


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("BOTS_DIGESTS_URI", str(tmp_path / "digests"))
    settings_path = tmp_path / "settings.json"
    monkeypatch.setenv("BOTS_DIGEST_SETTINGS_URI", f"file://{settings_path}")
    emails: List[Dict] = []
    alerts: List[str] = []
    monkeypatch.setattr(
        lam, "send_bots_digest_email", lambda to, digest, include: emails.append({"to": to, "digest": digest})
    )
    monkeypatch.setattr(digest_delivery, "_default_sender", alerts.append)

    def write_settings(owner_settings):
        settings_path.write_text(json.dumps(owner_settings))

    return {"emails": emails, "alerts": alerts, "settings": write_settings}


def test_weekly_digest_saved_and_emailed_on_monday_only(env):
    person = {"email": "alex@example.com"}
    tuesday = lam.run_owner("alex", person, FakeSource([_item()]), TUESDAY)
    assert tuesday == {"alerted": 0, "saved": False, "emailed": False}
    assert digest_store.load_latest("alex") is None

    monday = lam.run_owner("alex", person, FakeSource([_item()]), MONDAY)
    assert monday["saved"] and monday["emailed"]
    assert env["emails"][0]["to"] == "alex@example.com"
    assert digest_store.load_latest("alex").items[0].dedupe_key == "guardian:sept"


def test_force_and_monthly_due_days(env):
    env["settings"]({"alex": {"period": "monthly"}})
    assert lam.run_owner("alex", {}, FakeSource([]), MONDAY)["saved"] is False
    assert lam.run_owner("alex", {}, FakeSource([]), MONDAY, force=True)["saved"] is True
    first = datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert lam.run_owner("alex", {}, FakeSource([]), first)["saved"] is True


def test_empty_digest_not_sent_unless_opted_in(env):
    person = {"email": "alex@example.com"}
    assert lam.run_owner("alex", person, FakeSource([]), MONDAY)["emailed"] is False
    env["settings"]({"alex": {"send_when_empty": True}})
    assert lam.run_owner("alex", person, FakeSource([]), MONDAY)["emailed"] is True


def test_immediate_alert_fires_and_item_still_in_next_digest(env):
    env["settings"]({"alex": {"alert_immediately_for": {"guardian": ["high"]}}})
    source = FakeSource([_item()])

    assert lam.run_owner("alex", {"email": "alex@example.com"}, source, TUESDAY)["alerted"] == 1
    assert env["alerts"] == ["[high] September contribution of [amount hidden] not received"]

    monday = lam.run_owner("alex", {"email": "alex@example.com"}, source, MONDAY)
    assert monday["alerted"] == 0  # no repeat while still open
    assert [i.dedupe_key for i in env["emails"][0]["digest"].items] == ["guardian:sept"]


def test_run_digest_reports_per_owner_failures(env, monkeypatch):
    monkeypatch.setattr(
        lam,
        "list_portfolios",
        lambda: [{"owner": "alex", "person": {}}, {"owner": "bob", "person": {}}],
    )
    published = []
    monkeypatch.setattr(lam, "publish_sns_alert", published.append)
    real = lam.run_owner

    def flaky(owner, *args, **kwargs):
        if owner == "bob":
            raise RuntimeError("boom")
        return real(owner, *args, **kwargs)

    monkeypatch.setattr(lam, "run_owner", flaky)
    result = lam.run_digest({}, source=FakeSource([]))
    assert result == {"owners": 1, "errors": ["bob: RuntimeError"]}
    assert published and published[0]["ticker"] == "bots-digest"


def test_owner_filter(env, monkeypatch):
    monkeypatch.setenv("BOTS_DIGEST_OWNERS", "alex")
    monkeypatch.setattr(lam, "list_portfolios", lambda: [{"owner": "alex"}, {"owner": "bob"}])
    assert lam.run_digest({"force": True}, source=FakeSource([]))["owners"] == 1
