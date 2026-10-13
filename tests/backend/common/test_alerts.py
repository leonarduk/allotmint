"""Recent alerts survive a backend restart (#10802)."""

import importlib
import json
import sys
from types import SimpleNamespace

import pytest

import backend.common.alerts as alerts


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(alerts.config, "sns_topic_arn", None, raising=False)
    alerts.clear_state()
    yield
    alerts.clear_state()


def _restart():
    """Simulate a process restart: reload the module, dropping in-memory state."""
    return importlib.reload(alerts)


def _history_path(tmp_path):
    return tmp_path / "alerts" / "recent_alerts.json"


def test_alert_survives_restart(tmp_path):
    alerts.publish_alert({"ticker": "NESF.L", "message": "NESF.L down 34% from cost"})

    reloaded = _restart()

    recent = reloaded.get_recent_alerts()
    assert [a["message"] for a in recent] == ["NESF.L down 34% from cost"]
    assert recent[0]["ticker"] == "NESF.L"
    assert "timestamp" in recent[0]
    assert _history_path(tmp_path).exists()


def test_dedup_holds_across_restart():
    alert = {"ticker": "ABC", "message": "hello"}
    alerts.publish_alert(alert.copy())

    reloaded = _restart()
    reloaded.publish_alert(alert.copy())

    assert len(reloaded.get_recent_alerts()) == 1


def test_throttled_signature_is_persisted(monkeypatch):
    monkeypatch.setattr(alerts.config, "sns_topic_arn", "arn:example")
    sns = SimpleNamespace(publish=lambda **kwargs: None)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda name: sns))
    alerts.publish_alert({"instrument": "IBM", "state": True, "message": "a"})
    # Same state again: throttled, not listed, but its signature is seen.
    alerts.publish_alert({"instrument": "IBM", "state": True, "message": "b"})

    alerts.clear_state()  # restart without reload keeps the monkeypatched config

    alerts.publish_alert({"instrument": "IBM", "state": False, "message": "b"})
    assert [a["message"] for a in alerts.get_recent_alerts()] == ["a"]


def test_retention_caps_stored_alerts(tmp_path, monkeypatch):
    monkeypatch.setattr(alerts, "MAX_STORED_ALERTS", 3)
    monkeypatch.setattr(alerts, "MAX_STORED_SIGNATURES", 4)
    for i in range(6):
        alerts.publish_alert({"ticker": f"T{i}", "message": f"m{i}"})

    stored = json.loads(_history_path(tmp_path).read_text())
    assert [a["message"] for a in stored["alerts"]] == ["m3", "m4", "m5"]
    assert len(stored["signatures"]) == 4

    alerts.clear_state()
    assert [a["message"] for a in alerts.get_recent_alerts()] == ["m3", "m4", "m5"]
    assert [a["message"] for a in alerts.get_recent_alerts(limit=1)] == ["m5"]


def test_failed_read_does_not_wipe_memory(monkeypatch):
    alerts.publish_alert({"ticker": "X", "message": "kept"})
    monkeypatch.setattr(alerts, "_storage", lambda: SimpleNamespace(load=lambda: {}, save=lambda data: None))

    assert [a["message"] for a in alerts.get_recent_alerts()] == ["kept"]


def test_save_failure_is_logged_not_raised(monkeypatch, caplog):
    def boom(data):
        raise OSError("disk full")

    monkeypatch.setattr(alerts, "_storage", lambda: SimpleNamespace(load=lambda: {}, save=boom))
    with caplog.at_level("WARNING"):
        alerts.publish_alert({"ticker": "Y", "message": "still listed"})

    assert "Failed to persist alerts" in caplog.text
    assert [a["message"] for a in alerts.get_recent_alerts()] == ["still listed"]


def test_s3_location_when_data_bucket_set(monkeypatch):
    monkeypatch.delenv(alerts.ALERTS_HISTORY_ENV, raising=False)
    monkeypatch.setenv("DATA_BUCKET", "my-bucket")
    assert alerts._history_uri() == "s3://my-bucket/alerts/recent_alerts.json"
