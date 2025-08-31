import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import backend.common.alerts as alerts


@pytest.fixture(autouse=True)
def clear_alert_state():
    alerts.clear_state()
    yield
    alerts.clear_state()


def test_publish_alert_without_config(monkeypatch, caplog):
    monkeypatch.setattr(alerts.config, "sns_topic_arn", None, raising=False)
    with caplog.at_level("INFO"):
        alerts.publish_sns_alert({"message": "hi"})
    assert alerts._RECENT_ALERTS[0]["message"] == "hi"
    assert "SNS topic ARN not configured" in caplog.text
    assert alerts._LAST_ALERT_STATE == {}
    assert alerts._LAST_ALERT_TIME == {}


def test_publish_alert_success(monkeypatch):
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
    def fake_client(name):
        assert name == "sns"
        return SimpleNamespace(publish=lambda **kwargs: None)

    monkeypatch.setattr(alerts.config, "sns_topic_arn", "arn:example")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

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
    def fake_client(name):
        assert name == "sns"
        return SimpleNamespace(publish=lambda **kwargs: None)

    monkeypatch.setattr(alerts.config, "sns_topic_arn", "arn:example")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

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


def test_publish_failure_does_not_throttle(monkeypatch):
    monkeypatch.setattr(alerts.config, "sns_topic_arn", "arn:example")

    def failing_client(name):
        assert name == "sns"
        def publish(**kwargs):
            raise Exception("boom")
        return SimpleNamespace(publish=publish)

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=failing_client))

    alerts.publish_sns_alert({"instrument": "IBM", "state": True, "message": "a"})
    assert alerts._LAST_ALERT_STATE == {}
    assert alerts._LAST_ALERT_TIME == {}

    sent = {}

    def success_client(name):
        assert name == "sns"
        return SimpleNamespace(publish=lambda TopicArn, Message: sent.update({"TopicArn": TopicArn, "Message": Message}))

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=success_client))

    alerts.publish_sns_alert({"instrument": "IBM", "state": True, "message": "b"})
    assert len(alerts._RECENT_ALERTS) == 2
    assert sent["Message"] == "b"
