import json
import sys
import types
import pytest

import backend.alerts as alerts


@pytest.fixture(autouse=True)
def clear_caches(monkeypatch):
    monkeypatch.setattr(alerts, "_USER_THRESHOLDS", {})
    monkeypatch.setattr(alerts, "_PUSH_SUBSCRIPTIONS", {})

def test_parse_thresholds_parses_valid_entries():
    data = {"a": "1.5", "b": 2, "c": 3.0}
    assert alerts._parse_thresholds(data) == {"a": 1.5, "b": 2.0, "c": 3.0}

def test_parse_thresholds_discards_invalid_entries():
    data = {"good": "1.5", "bad": "x", "also_bad": None, "num": 2}
    assert alerts._parse_thresholds(data) == {"good": 1.5, "num": 2.0}

def test_parse_thresholds_returns_empty_for_invalid_data():
    data = {"bad": "x", "also_bad": None}
    assert alerts._parse_thresholds(data) == {}


def test_parse_subscriptions_discards_non_dict_entries():
    data = {"u1": {"k": "v"}, "u2": "bad", "u3": 5}
    assert alerts._parse_subscriptions(data) == {"u1": {"k": "v"}}


def test_load_settings_uses_local_when_no_bucket(monkeypatch):
    local = {"a": "0.3", "b": "bad"}

    def loader():
        return local

    monkeypatch.setattr(alerts, "_data_bucket", lambda: None)
    monkeypatch.setattr(alerts, "_SETTINGS_STORAGE", types.SimpleNamespace(load=loader))

    alerts._load_settings()
    assert alerts._USER_THRESHOLDS == {"a": 0.3}


def test_load_settings_falls_back_to_local_on_s3_error(monkeypatch):
    local = {"a": "0.4", "b": "bad"}

    def loader():
        return local

    class BoomS3:
        def get_object(self, Bucket, Key):
            raise RuntimeError("boom")

    monkeypatch.setattr(alerts, "_data_bucket", lambda: "bucket")
    monkeypatch.setattr(alerts, "_s3_client", lambda: BoomS3())
    monkeypatch.setattr(alerts, "_SETTINGS_STORAGE", types.SimpleNamespace(load=loader))

    alerts._load_settings()
    assert alerts._USER_THRESHOLDS == {"a": 0.4}


def test_load_settings_uses_s3_when_available(monkeypatch):
    s3 = types.SimpleNamespace()

    def get_object(Bucket, Key):
        assert Bucket == "bucket"
        assert Key == alerts._THRESHOLDS_KEY
        data = json.dumps({"a": "0.6", "b": 0.7}).encode()
        return {"Body": types.SimpleNamespace(read=lambda: data)}

    s3.get_object = get_object

    def boom():
        raise AssertionError("local load should not be used")

    monkeypatch.setattr(alerts, "_data_bucket", lambda: "bucket")
    monkeypatch.setattr(alerts, "_s3_client", lambda: s3)
    monkeypatch.setattr(alerts, "_SETTINGS_STORAGE", types.SimpleNamespace(load=boom))

    alerts._load_settings()
    assert alerts._USER_THRESHOLDS == {"a": 0.6, "b": 0.7}


def test_save_settings_uses_local_when_no_bucket(monkeypatch):
    saved = {}

    def save(data):
        saved.update(data)

    def boom():
        raise AssertionError("S3 should not be used")

    monkeypatch.setattr(alerts, "_data_bucket", lambda: None)
    monkeypatch.setattr(alerts, "_s3_client", boom)
    monkeypatch.setattr(alerts, "_SETTINGS_STORAGE", types.SimpleNamespace(save=save))

    alerts._USER_THRESHOLDS = {"u": 0.8}
    alerts._save_settings()

    assert saved == {"u": 0.8}


def test_save_settings_writes_to_s3_when_configured(monkeypatch):
    puts = []

    class FakeS3:
        def get_object(self, Bucket, Key):
            data = json.dumps({"a": "0.1"}).encode()
            return {"Body": types.SimpleNamespace(read=lambda: data)}

        def put_object(self, Bucket, Key, Body):
            puts.append({"Bucket": Bucket, "Key": Key, "Body": Body})

    def boom(*args, **kwargs):
        raise AssertionError("local save should not be used")

    monkeypatch.setattr(alerts, "_data_bucket", lambda: "bucket")
    monkeypatch.setattr(alerts, "_s3_client", lambda: FakeS3())
    monkeypatch.setattr(alerts, "_SETTINGS_STORAGE", types.SimpleNamespace(save=boom))

    alerts._USER_THRESHOLDS = {"b": 0.2}
    alerts._save_settings()

    assert puts, "put_object was not called"
    saved = json.loads(puts[0]["Body"])
    assert saved == {"a": "0.1", "b": 0.2}
    assert alerts._USER_THRESHOLDS == {"a": 0.1, "b": 0.2}


def test_load_subscriptions_uses_local_when_no_bucket(monkeypatch):
    local = {"u1": {"x": 1}, "u2": "bad"}

    def loader():
        return local

    monkeypatch.setattr(alerts, "_data_bucket", lambda: None)
    monkeypatch.setattr(alerts, "_SUBSCRIPTIONS_STORAGE", types.SimpleNamespace(load=loader))

    alerts._load_subscriptions()
    assert alerts._PUSH_SUBSCRIPTIONS == {"u1": {"x": 1}}


def test_load_subscriptions_falls_back_to_local_on_s3_error(monkeypatch):
    local = {"u1": {"a": 1}, "u2": "bad"}

    def loader():
        return local

    class BoomS3:
        def get_object(self, Bucket, Key):
            raise RuntimeError("boom")

    monkeypatch.setattr(alerts, "_data_bucket", lambda: "bucket")
    monkeypatch.setattr(alerts, "_s3_client", lambda: BoomS3())
    monkeypatch.setattr(alerts, "_SUBSCRIPTIONS_STORAGE", types.SimpleNamespace(load=loader))

    alerts._load_subscriptions()
    assert alerts._PUSH_SUBSCRIPTIONS == {"u1": {"a": 1}}


def test_load_subscriptions_uses_s3_when_available(monkeypatch):
    s3 = types.SimpleNamespace()

    def get_object(Bucket, Key):
        assert Bucket == "bucket"
        assert Key == alerts._SUBSCRIPTIONS_KEY
        data = json.dumps({"u1": {"k": 1}, "u2": "bad"}).encode()
        return {"Body": types.SimpleNamespace(read=lambda: data)}

    s3.get_object = get_object

    def boom():
        raise AssertionError("local load should not be used")

    monkeypatch.setattr(alerts, "_data_bucket", lambda: "bucket")
    monkeypatch.setattr(alerts, "_s3_client", lambda: s3)
    monkeypatch.setattr(alerts, "_SUBSCRIPTIONS_STORAGE", types.SimpleNamespace(load=boom))

    alerts._load_subscriptions()
    assert alerts._PUSH_SUBSCRIPTIONS == {"u1": {"k": 1}}


def test_save_subscriptions_uses_local_when_no_bucket(monkeypatch):
    saved = {}

    def save(data):
        saved.update(data)

    def boom(*args, **kwargs):
        raise AssertionError("S3 should not be used")

    monkeypatch.setattr(alerts, "_data_bucket", lambda: None)
    monkeypatch.setattr(alerts, "_s3_client", boom)
    monkeypatch.setattr(alerts, "_SUBSCRIPTIONS_STORAGE", types.SimpleNamespace(save=save))

    alerts._PUSH_SUBSCRIPTIONS = {"u": {"a": 1}}
    alerts._save_subscriptions()

    assert saved == {"u": {"a": 1}}


def test_save_subscriptions_writes_to_s3_when_configured(monkeypatch):
    puts = []

    class FakeS3:
        def get_object(self, Bucket, Key):
            data = json.dumps({"u1": {"a": 1}}).encode()
            return {"Body": types.SimpleNamespace(read=lambda: data)}

        def put_object(self, Bucket, Key, Body):
            puts.append({"Bucket": Bucket, "Key": Key, "Body": Body})

    def boom(*args, **kwargs):
        raise AssertionError("local save should not be used")

    monkeypatch.setattr(alerts, "_data_bucket", lambda: "bucket")
    monkeypatch.setattr(alerts, "_s3_client", lambda: FakeS3())
    monkeypatch.setattr(alerts, "_SUBSCRIPTIONS_STORAGE", types.SimpleNamespace(save=boom))

    alerts._PUSH_SUBSCRIPTIONS = {"u2": {"b": 2}}
    alerts._save_subscriptions()

    assert puts, "put_object was not called"
    saved = json.loads(puts[0]["Body"])
    assert saved == {"u1": {"a": 1}, "u2": {"b": 2}}
    assert alerts._PUSH_SUBSCRIPTIONS == {"u1": {"a": 1}, "u2": {"b": 2}}


def test_send_push_notification_no_subscriptions(monkeypatch):
    msgs = []

    monkeypatch.setattr(alerts, "iter_push_subscriptions", lambda: [])
    monkeypatch.setattr(alerts, "publish_alert", lambda m: msgs.append(m))

    alerts.send_push_notification("hi")
    assert msgs == [{"message": "hi"}]


def test_send_push_notification_missing_vapid(monkeypatch):
    msgs = []

    monkeypatch.setattr(alerts, "iter_push_subscriptions", lambda: [{}])
    monkeypatch.setattr(alerts, "publish_alert", lambda m: msgs.append(m))
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("VAPID_EMAIL", raising=False)

    alerts.send_push_notification("hello")
    assert msgs == [{"message": "hello"}]


def test_send_push_notification_webpush_success(monkeypatch):
    called = []

    monkeypatch.setattr(alerts, "iter_push_subscriptions", lambda: [{"endpoint": "e"}])
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "key")
    monkeypatch.setenv("VAPID_EMAIL", "x@example.com")
    monkeypatch.setattr(alerts, "publish_alert", lambda m: called.append(("sns", m)))

    def webpush(**kwargs):
        called.append(("push", kwargs["data"]))

    monkeypatch.setitem(sys.modules, "pywebpush", types.SimpleNamespace(webpush=webpush))

    alerts.send_push_notification("hi")

    assert ("push", "hi") in called
    assert all(kind != "sns" for kind, _ in called)


def test_send_push_notification_webpush_failure_falls_back(monkeypatch):
    msgs = []

    monkeypatch.setattr(alerts, "iter_push_subscriptions", lambda: [{"endpoint": "e"}])
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "key")
    monkeypatch.setenv("VAPID_EMAIL", "x@example.com")
    monkeypatch.setattr(alerts, "publish_alert", lambda m: msgs.append(m))

    def webpush(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setitem(sys.modules, "pywebpush", types.SimpleNamespace(webpush=webpush))

    alerts.send_push_notification("hi")
    assert msgs == [{"message": "hi"}]


def test_evaluate_drift_publishes_alert(monkeypatch):
    msgs = []
    monkeypatch.setattr(alerts, "publish_alert", lambda m: msgs.append(m))

    result = alerts.evaluate_drift("u", 100, 110, threshold=0.05, metric="price")
    assert result.triggered and round(result.drift_pct, 4) == 0.1
    assert msgs and msgs[0]["user"] == "u"


def test_evaluate_drift_uses_user_specific_default(monkeypatch):
    msgs = []
    monkeypatch.setattr(alerts, "publish_alert", lambda m: msgs.append(m))
    alerts._USER_THRESHOLDS = {"u": 0.2}

    result = alerts.evaluate_drift("u", 100, 110)
    assert not result.triggered
    assert msgs == []
