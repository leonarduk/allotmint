import types
import pytest

import backend.alerts as alerts


@pytest.fixture(autouse=True)
def clear_caches(monkeypatch):
    monkeypatch.setattr(alerts, "_USER_THRESHOLDS", {})
    monkeypatch.setattr(alerts, "_PUSH_SUBSCRIPTIONS", {})


def test_parse_thresholds_discards_invalid_entries():
    data = {"good": "1.5", "bad": "x", "also_bad": None, "num": 2}
    assert alerts._parse_thresholds(data) == {"good": 1.5, "num": 2.0}


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
