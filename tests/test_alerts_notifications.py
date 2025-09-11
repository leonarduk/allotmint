import sys
import types
import pytest
import backend.alerts as alerts


@pytest.fixture(autouse=True)
def clear_state(monkeypatch):
    monkeypatch.setattr(alerts, "_USER_THRESHOLDS", {})
    monkeypatch.setattr(alerts, "_PUSH_SUBSCRIPTIONS", {})


def test_send_push_notification_no_subscriptions(monkeypatch):
    called = {}
    monkeypatch.setattr(alerts, "iter_push_subscriptions", lambda: [])
    monkeypatch.setattr(alerts, "publish_alert", lambda msg: called.update(msg))

    alerts.send_push_notification("hi")

    assert called["message"] == "hi"


def test_send_push_notification_missing_vapid(monkeypatch):
    called = {}
    monkeypatch.setattr(alerts, "iter_push_subscriptions", lambda: [{}])
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("VAPID_EMAIL", raising=False)
    monkeypatch.setattr(alerts, "publish_alert", lambda msg: called.update(msg))

    alerts.send_push_notification("hi")

    assert called["message"] == "hi"


def test_send_push_notification_webpush_success(monkeypatch):
    webpush_calls = []
    monkeypatch.setattr(alerts, "iter_push_subscriptions", lambda: [{"endpoint": "x"}])
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "key")
    monkeypatch.setenv("VAPID_EMAIL", "email@example.com")

    def webpush(subscription_info, data, vapid_private_key, vapid_claims):
        webpush_calls.append((subscription_info, data, vapid_private_key, vapid_claims))

    monkeypatch.setitem(sys.modules, "pywebpush", types.SimpleNamespace(webpush=webpush))

    published = {}
    monkeypatch.setattr(alerts, "publish_alert", lambda msg: published.update(msg))

    alerts.send_push_notification("msg")

    assert webpush_calls
    assert published == {}


def test_send_push_notification_webpush_failure_fallback(monkeypatch):
    monkeypatch.setattr(alerts, "iter_push_subscriptions", lambda: [{"endpoint": "x"}])
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "key")
    monkeypatch.setenv("VAPID_EMAIL", "email@example.com")

    def webpush(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setitem(sys.modules, "pywebpush", types.SimpleNamespace(webpush=webpush))

    published = {}
    monkeypatch.setattr(alerts, "publish_alert", lambda msg: published.update(msg))

    alerts.send_push_notification("msg")

    assert published["message"] == "msg"


def test_evaluate_drift_publishes_alert(monkeypatch):
    published = {}
    monkeypatch.setattr(alerts, "publish_alert", lambda msg: published.update(msg))
    alerts._USER_THRESHOLDS = {"u": 0.05}

    result = alerts.evaluate_drift("u", baseline=100, value=110)

    assert result.triggered and pytest.approx(result.drift_pct, 0.0001) == 0.1
    assert published["user"] == "u"


def test_evaluate_drift_uses_user_threshold_default(monkeypatch):
    published = {}
    monkeypatch.setattr(alerts, "publish_alert", lambda msg: published.update(msg))
    alerts._USER_THRESHOLDS = {"u": 0.2}

    result = alerts.evaluate_drift("u", baseline=100, value=115)

    assert not result.triggered
    assert published == {}
