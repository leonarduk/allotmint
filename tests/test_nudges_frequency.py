import backend.nudges as nudge_utils
from backend.common.storage import get_storage


def _setup_tmp_storage(tmp_path, monkeypatch):
    storage = get_storage(f"file://{tmp_path / 'nudges.json'}")
    monkeypatch.setattr(nudge_utils, "_SUBSCRIPTION_STORAGE", storage)
    nudge_utils._SUBSCRIPTIONS.clear()
    nudge_utils._RECENT_NUDGES.clear()


def test_frequency_clamped(tmp_path, monkeypatch):
    _setup_tmp_storage(tmp_path, monkeypatch)
    nudge_utils.set_user_nudge("alice", 0)
    assert nudge_utils._SUBSCRIPTIONS["alice"]["frequency"] == 1

    _setup_tmp_storage(tmp_path, monkeypatch)
    nudge_utils.set_user_nudge("alice", 31)
    assert nudge_utils._SUBSCRIPTIONS["alice"]["frequency"] == 30


def test_snooze_user_sets_future_timestamp(tmp_path, monkeypatch):
    _setup_tmp_storage(tmp_path, monkeypatch)
    nudge_utils.set_user_nudge("bob", 7)

    start = nudge_utils.datetime.now(nudge_utils.UTC)
    nudge_utils.snooze_user("bob", 3)

    snoozed_until = nudge_utils._SUBSCRIPTIONS["bob"]["snoozed_until"]
    assert snoozed_until is not None

    until = nudge_utils.datetime.fromisoformat(snoozed_until)
    assert until >= start + nudge_utils.timedelta(days=3)


def test_iter_due_users_respects_snooze(tmp_path, monkeypatch):
    _setup_tmp_storage(tmp_path, monkeypatch)

    now = nudge_utils.datetime(2024, 1, 10, tzinfo=nudge_utils.UTC)
    nudge_utils.set_user_nudge("new", 5)
    nudge_utils.set_user_nudge("due", 2)
    nudge_utils.set_user_nudge("recent", 5)
    nudge_utils.set_user_nudge("snoozed", 1)

    nudge_utils._SUBSCRIPTIONS["due"]["last_sent"] = (now - nudge_utils.timedelta(days=3)).isoformat()
    nudge_utils._SUBSCRIPTIONS["recent"]["last_sent"] = (now - nudge_utils.timedelta(days=1)).isoformat()
    nudge_utils._SUBSCRIPTIONS["snoozed"]["last_sent"] = (now - nudge_utils.timedelta(days=10)).isoformat()
    snooze_end = (now + nudge_utils.timedelta(days=1)).isoformat()
    nudge_utils._SUBSCRIPTIONS["snoozed"]["snoozed_until"] = snooze_end
    nudge_utils._save_state()

    due_users = set(nudge_utils.iter_due_users(now))
    assert due_users == {"new", "due"}

    _setup_tmp_storage(tmp_path, monkeypatch)

    later = now + nudge_utils.timedelta(days=2)
    due_users_later = set(nudge_utils.iter_due_users(later))
    assert due_users_later == {"new", "due", "snoozed"}

