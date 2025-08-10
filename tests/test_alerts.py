import sys
from types import SimpleNamespace
import pytest

import backend.common.alerts as alerts


def test_publish_alert_requires_config(monkeypatch):
    alerts._RECENT_ALERTS.clear()
    monkeypatch.setattr(alerts.config, "sns_topic_arn", None, raising=False)
    with pytest.raises(RuntimeError):
        alerts.publish_alert({"message": "hi"})


def test_publish_alert_success(monkeypatch):
    alerts._RECENT_ALERTS.clear()
    sent = {}

    def fake_client(name):
        assert name == "sns"
        return SimpleNamespace(publish=lambda TopicArn, Message: sent.update({"TopicArn": TopicArn, "Message": Message}))

    monkeypatch.setattr(alerts.config, "sns_topic_arn", "arn:example")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))

    alerts.publish_alert({"message": "hello"})
    assert alerts._RECENT_ALERTS[0]["message"] == "hello"
    assert sent["TopicArn"] == "arn:example" and sent["Message"] == "hello"
