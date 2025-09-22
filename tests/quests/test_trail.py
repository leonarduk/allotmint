import pytest
from datetime import date, timedelta

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
    response = trail.get_tasks("alice")
    tasks = response["tasks"]
    assert [t["id"] for t in tasks] == [t["id"] for t in trail.DEFAULT_TASKS]
    assert all(not t["completed"] for t in tasks)
    assert response["xp"] == 0
    assert response["streak"] == 0
    assert response["daily_totals"][response["today"]]["completed"] == 0
    assert response["daily_totals"][response["today"]]["total"] == trail.DAILY_TASK_COUNT


def test_get_tasks_with_completions(memory_storage):
    today = date.today().isoformat()
    memory_storage["bob"] = {
        "once": ["create_goal"],
        "daily": {today: ["check_market"]},
        "xp": trail.DAILY_XP_REWARD,
        "streak": 2,
        "last_completed_day": today,
        "daily_totals": {today: {"completed": 1, "total": trail.DAILY_TASK_COUNT}},
    }
    response = trail.get_tasks("bob")
    completed = {t["id"]: t["completed"] for t in response["tasks"]}
    assert completed["create_goal"] is True
    assert completed["check_market"] is True
    for task in trail.DEFAULT_TASKS:
        if task["id"] not in {"create_goal", "check_market"}:
            assert completed[task["id"]] is False
    assert response["xp"] == trail.DAILY_XP_REWARD
    assert response["streak"] == 2
    assert response["daily_totals"][response["today"]]["completed"] == 1
    assert response["daily_totals"][response["today"]]["total"] == trail.DAILY_TASK_COUNT


def test_mark_complete_records_once_and_daily(memory_storage):
    user = "carol"
    today = date.today().isoformat()

    result = trail.mark_complete(user, "check_market")
    assert memory_storage[user]["daily"][today] == ["check_market"]
    assert result["xp"] == trail.DAILY_XP_REWARD
    assert result["daily_totals"][today]["completed"] == 1

    result = trail.mark_complete(user, "check_market")
    assert memory_storage[user]["daily"][today] == ["check_market"]
    assert result["xp"] == trail.DAILY_XP_REWARD

    result = trail.mark_complete(user, "create_goal")
    assert memory_storage[user]["once"] == ["create_goal"]
    assert result["xp"] == trail.DAILY_XP_REWARD + trail.ONCE_XP_REWARD

    result = trail.mark_complete(user, "create_goal")
    assert memory_storage[user]["once"] == ["create_goal"]
    assert result["xp"] == trail.DAILY_XP_REWARD + trail.ONCE_XP_REWARD

    with pytest.raises(KeyError):
        trail.mark_complete(user, "unknown")


def test_mark_complete_updates_streak(memory_storage):
    user = "dave"
    today = date.today()
    today_str = today.isoformat()
    yesterday = (today - timedelta(days=1)).isoformat()

    memory_storage[user] = {
        "once": [],
        "daily": {yesterday: trail.DAILY_TASK_IDS},
        "xp": len(trail.DAILY_TASK_IDS) * trail.DAILY_XP_REWARD,
        "streak": 1,
        "last_completed_day": yesterday,
        "daily_totals": {
            yesterday: {
                "completed": trail.DAILY_TASK_COUNT,
                "total": trail.DAILY_TASK_COUNT,
            }
        },
    }

    for task_id in trail.DAILY_TASK_IDS:
        response = trail.mark_complete(user, task_id)

    assert response["streak"] == 2
    assert response["xp"] == len(trail.DAILY_TASK_IDS) * trail.DAILY_XP_REWARD * 2
    assert response["daily_totals"][today_str]["completed"] == trail.DAILY_TASK_COUNT
    assert response["daily_totals"][today_str]["total"] == trail.DAILY_TASK_COUNT
