from backend import nudges as nudge_utils
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
    nudge_utils.set_user_nudge("alice", 31)
    assert nudge_utils._SUBSCRIPTIONS["alice"]["frequency"] == 30

