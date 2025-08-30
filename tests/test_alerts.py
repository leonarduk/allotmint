import sys
from types import SimpleNamespace

import backend.common.alerts as alerts


def test_publish_alert_without_config(monkeypatch, caplog):
    alerts._RECENT_ALERTS.clear()
    alerts._RECENT_ALERT_SIGNATURES.clear()
    monkeypatch.setattr(alerts.config, "sns_topic_arn", None, raising=False)
    with caplog.at_level("INFO"):
        alerts.publish_sns_alert({"message": "hi"})
    assert alerts._RECENT_ALERTS[0]["message"] == "hi"
    assert "SNS topic ARN not configured" in caplog.text


def test_publish_alert_success(monkeypatch):
    alerts._RECENT_ALERTS.clear()
    alerts._RECENT_ALERT_SIGNATURES.clear()
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
