import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import backend.common.alerts as alerts


def test_publish_alert_without_config(monkeypatch, caplog):
    alerts._RECENT_ALERTS.clear()
    alerts._LAST_ALERT_STATE.clear()
    alerts._LAST_ALERT_TIME.clear()
    monkeypatch.setattr(alerts.config, "sns_topic_arn", None, raising=False)
    with caplog.at_level("INFO"):
        alerts.publish_sns_alert({"message": "hi"})
    assert alerts._RECENT_ALERTS[0]["message"] == "hi"
    assert "SNS topic ARN not configured" in caplog.text


def test_publish_alert_success(monkeypatch):
    alerts._RECENT_ALERTS.clear()
    alerts._LAST_ALERT_STATE.clear()
    alerts._LAST_ALERT_TIME.clear()
    sent = {}

    def fake_client(name):
        assert name == "sns"
        return SimpleNamespace(
            publish=lambda TopicArn, Message: sent.update({"TopicArn": TopicArn, "Message": Message})
        )

    monkeypatch.setattr(alerts.config, "sns_topic_arn", "arn:example")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    alerts.publish_sns_alert({"message": "hello"})
    assert alerts._RECENT_ALERTS[0]["message"] == "hello"
    assert sent["TopicArn"] == "arn:example" and sent["Message"] == "hello"


def test_per_instrument_throttling(monkeypatch):
    alerts._RECENT_ALERTS.clear()
    alerts._LAST_ALERT_STATE.clear()
    alerts._LAST_ALERT_TIME.clear()

    monkeypatch.setattr(alerts.config, "sns_topic_arn", None, raising=False)

    class DummyDatetime(datetime):
        current = datetime(2024, 1, 1, 0, 0, 0)

        @classmethod
        def utcnow(cls):
            return cls.current

    monkeypatch.setattr(alerts, "datetime", DummyDatetime)

    alerts.publish_sns_alert({"instrument": "IBM", "state": True, "message": "a"})
    assert len(alerts._RECENT_ALERTS) == 1

    DummyDatetime.current += timedelta(minutes=30)
    alerts.publish_sns_alert({"instrument": "IBM", "state": False, "message": "b"})
    assert len(alerts._RECENT_ALERTS) == 1  # throttled

    alerts.publish_sns_alert({"instrument": "AAPL", "state": True, "message": "c"})
    assert len(alerts._RECENT_ALERTS) == 2  # different instrument

    DummyDatetime.current += timedelta(minutes=40)
    alerts.publish_sns_alert({"instrument": "IBM", "state": False, "message": "d"})
    assert len(alerts._RECENT_ALERTS) == 3


def test_publish_only_on_state_change(monkeypatch):
    alerts._RECENT_ALERTS.clear()
    alerts._LAST_ALERT_STATE.clear()
    alerts._LAST_ALERT_TIME.clear()

    monkeypatch.setattr(alerts.config, "sns_topic_arn", None, raising=False)

    class DummyDatetime(datetime):
        current = datetime(2024, 1, 1, 0, 0, 0)

        @classmethod
        def utcnow(cls):
            return cls.current

    monkeypatch.setattr(alerts, "datetime", DummyDatetime)

    alerts.publish_sns_alert({"instrument": "IBM", "state": True, "message": "a"})
    assert len(alerts._RECENT_ALERTS) == 1

    DummyDatetime.current += timedelta(hours=2)
    alerts.publish_sns_alert({"instrument": "IBM", "state": True, "message": "b"})
    assert len(alerts._RECENT_ALERTS) == 1  # no state change

    alerts.publish_sns_alert({"instrument": "IBM", "state": False, "message": "c"})
    assert len(alerts._RECENT_ALERTS) == 2
