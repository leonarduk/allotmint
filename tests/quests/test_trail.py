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
    data = trail.get_tasks("alice")
    tasks = data["tasks"]
    assert [t["id"] for t in tasks] == [t["id"] for t in trail.DEFAULT_TASKS]
    assert all(not t["completed"] for t in tasks)
    assert data["xp"] == 0
    assert data["streak"] == 0
    assert data["today_completed"] == 0
    assert data["today_total"] == len(trail.DAILY_TASK_IDS)
    assert data["daily_totals"] == {}


def test_get_tasks_with_completions(memory_storage):
    today = date.today().isoformat()
    memory_storage["bob"] = {"once": ["create_goal"], "daily": {today: ["check_market"]}}
    data = trail.get_tasks("bob")
    completed = {t["id"]: t["completed"] for t in data["tasks"]}
    assert completed["create_goal"] is True
    assert completed["check_market"] is True
    for task in trail.DEFAULT_TASKS:
        if task["id"] not in {"create_goal", "check_market"}:
            assert completed[task["id"]] is False
    assert data["xp"] == 0
    assert data["streak"] == 0
    assert data["daily_totals"][today] == 1


def test_mark_complete_records_once_and_daily(memory_storage):
    user = "carol"
    today = date.today().isoformat()

    result = trail.mark_complete(user, "check_market")
    assert result["today_completed"] == 1
    assert result["xp"] == trail.DAILY_XP
    assert memory_storage[user]["daily"][today] == ["check_market"]
    result = trail.mark_complete(user, "check_market")
    assert result["xp"] == trail.DAILY_XP
    assert memory_storage[user]["daily"][today] == ["check_market"]

    result = trail.mark_complete(user, "create_goal")
    assert result["xp"] == trail.DAILY_XP + trail.ONCE_XP
    assert memory_storage[user]["once"] == ["create_goal"]
    result = trail.mark_complete(user, "create_goal")
    assert result["xp"] == trail.DAILY_XP + trail.ONCE_XP
    assert memory_storage[user]["once"] == ["create_goal"]

    with pytest.raises(KeyError):
        trail.mark_complete(user, "unknown")


def test_daily_completion_updates_streak_and_bonus(memory_storage):
    user = "dave"
    today = date.today().isoformat()

    first = trail.mark_complete(user, "check_market")
    assert first["streak"] == 0
    second = trail.mark_complete(user, "review_portfolio")

    assert second["streak"] == 1
    assert second["today_completed"] == len(trail.DAILY_TASK_IDS)
    expected_xp = trail.DAILY_XP * len(trail.DAILY_TASK_IDS) + trail.DAILY_COMPLETION_BONUS
    assert second["xp"] == expected_xp
    assert memory_storage[user]["daily_totals"][today] == len(trail.DAILY_TASK_IDS)
