import pytest

from backend import nudges as nudge_utils
from backend.common.storage import get_storage


def test_nudges_persist_and_load(tmp_path, monkeypatch):
    storage = get_storage(f"file://{tmp_path / 'nudges.json'}")
    monkeypatch.setattr(nudge_utils, "_SUBSCRIPTION_STORAGE", storage)
    nudge_utils._SUBSCRIPTIONS.clear()
    nudge_utils._RECENT_NUDGES.clear()

    nudge_utils.set_user_nudge("alice", 1)
    nudge_utils.send_due_nudges()

    nudge_utils._SUBSCRIPTIONS.clear()
    nudge_utils._RECENT_NUDGES.clear()

    nudges = nudge_utils.get_recent_nudges()
    assert any(n["id"] == "alice" for n in nudges)
