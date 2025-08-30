import backend.common.alerts as alerts


def test_get_recent_alerts_skips_duplicates(monkeypatch):
    alerts._RECENT_ALERTS.clear()
    alerts._RECENT_ALERT_SIGNATURES.clear()
    monkeypatch.setattr(alerts.config, "sns_topic_arn", None, raising=False)
    alert = {"ticker": "ABC", "message": "hello"}
    alerts.publish_alert(alert.copy())
    alerts.publish_alert(alert.copy())
    recent = alerts.get_recent_alerts()
    assert len(recent) == 1
    assert recent[0]["ticker"] == "ABC" and recent[0]["message"] == "hello"
