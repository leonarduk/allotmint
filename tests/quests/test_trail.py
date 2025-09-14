import pytest
from datetime import date

from backend.common.storage import get_storage
from backend.quests import trail


@pytest.fixture
def memory_storage(monkeypatch):
    """Provide in-memory storage by patching the trail module."""
    data = {}
    storage = get_storage("file://trail.json")

    def load():
        return data

    def save(new_data):
        data.update(new_data)

    monkeypatch.setattr(storage, "load", load)
    monkeypatch.setattr(storage, "save", save)
    monkeypatch.setattr(trail, "_TRAIL_STORAGE", storage)
    monkeypatch.setattr(trail, "_DATA", {})
    return data


def test_get_tasks_returns_defaults(memory_storage):
    tasks = trail.get_tasks("alice")
    assert [t["id"] for t in tasks] == [t["id"] for t in trail.DEFAULT_TASKS]
    assert all(not t["completed"] for t in tasks)


def test_get_tasks_with_completions(memory_storage):
    today = date.today().isoformat()
    memory_storage["bob"] = {"once": ["create_goal"], "daily": {today: ["check_market"]}}
    tasks = trail.get_tasks("bob")
    completed = {t["id"]: t["completed"] for t in tasks}
    assert completed["create_goal"] is True
    assert completed["check_market"] is True
    for task in trail.DEFAULT_TASKS:
        if task["id"] not in {"create_goal", "check_market"}:
            assert completed[task["id"]] is False


def test_mark_complete_records_once_and_daily(memory_storage):
    user = "carol"
    today = date.today().isoformat()

    trail.mark_complete(user, "check_market")
    assert memory_storage[user]["daily"][today] == ["check_market"]
    trail.mark_complete(user, "check_market")
    assert memory_storage[user]["daily"][today] == ["check_market"]

    trail.mark_complete(user, "create_goal")
    assert memory_storage[user]["once"] == ["create_goal"]
    trail.mark_complete(user, "create_goal")
    assert memory_storage[user]["once"] == ["create_goal"]

    with pytest.raises(KeyError):
        trail.mark_complete(user, "unknown")
