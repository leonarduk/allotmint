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

    # The signature is ticker|message (no ticker here), so this matches the
    # throttled "b" above and is skipped as a duplicate despite the new state.
    alerts.publish_alert({"instrument": "IBM", "state": False, "message": "b"})
    assert [a["message"] for a in alerts.get_recent_alerts()] == ["a"]


def test_hourly_throttle_holds_across_restart(monkeypatch):
    monkeypatch.setattr(alerts.config, "sns_topic_arn", "arn:example")
    sns = SimpleNamespace(publish=lambda **kwargs: None)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda name: sns))
    alerts.publish_alert({"instrument": "IBM", "state": True, "message": "crossed"})

    alerts.clear_state()  # restart: in-memory throttle state is gone

    # State changed, but it is within the hour of the last published alert.
    alerts.publish_alert({"instrument": "IBM", "state": False, "message": "recovered"})
    assert [a["message"] for a in alerts.get_recent_alerts()] == ["crossed"]
    assert alerts._LAST_ALERT_STATE == {"IBM": True}


def test_hourly_throttle_without_sns_holds_across_restart():
    # Local dev: no SNS topic, so the in-app list is the only delivery.
    alerts.publish_alert({"instrument": "NESF.L", "state": True, "message": "down"})

    alerts.clear_state()

    alerts.publish_alert({"instrument": "NESF.L", "state": False, "message": "back"})
    assert [a["message"] for a in alerts.get_recent_alerts()] == ["down"]


def test_naive_throttle_time_is_treated_as_utc(tmp_path):
    path = _history_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    naive_now = alerts.datetime.now(alerts.UTC).replace(tzinfo=None).isoformat()
    doc = {"alerts": [], "signatures": [], "throttle": {"IBM": {"state": True, "time": naive_now}}}
    path.write_text(json.dumps(doc))

    alerts.publish_alert({"instrument": "IBM", "state": False, "message": "flip"})

    assert alerts.get_recent_alerts() == []  # within the hour, no TypeError


def test_reads_alerts_written_by_another_process(tmp_path):
    alerts.publish_alert({"ticker": "A", "message": "mine"})
    path = _history_path(tmp_path)
    doc = json.loads(path.read_text())
    doc["alerts"].append({"ticker": "B", "message": "theirs", "timestamp": "2026-10-13T00:00:00+00:00"})
    path.write_text(json.dumps(doc))

    assert [a["message"] for a in alerts.get_recent_alerts()] == ["mine", "theirs"]


def test_stored_throttle_replaces_memory(tmp_path):
    alerts._LAST_ALERT_STATE["OLD"] = True
    alerts._LAST_ALERT_TIME["OLD"] = alerts.datetime.now(alerts.UTC)
    path = _history_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"alerts": [{"message": "x"}], "signatures": ["s"]}))

    alerts.get_recent_alerts()

    assert alerts._LAST_ALERT_STATE == {} and alerts._LAST_ALERT_TIME == {}


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


def test_explicit_uri_wins_over_data_bucket(monkeypatch, tmp_path):
    uri = f"file://{tmp_path / 'elsewhere.json'}"
    monkeypatch.setenv(alerts.ALERTS_HISTORY_ENV, uri)
    monkeypatch.setenv("DATA_BUCKET", "my-bucket")
    assert alerts._history_uri() == uri


def test_s3_location_when_data_bucket_set(monkeypatch):
    monkeypatch.delenv(alerts.ALERTS_HISTORY_ENV, raising=False)
    monkeypatch.setenv("DATA_BUCKET", "my-bucket")
    assert alerts._history_uri() == "s3://my-bucket/alerts/recent_alerts.json"
