from datetime import date, timedelta

import pytest

from backend import alerts
from backend.common.storage import get_storage
from backend.quests import trail


@pytest.fixture
def memory_storage(monkeypatch):
    """Provide in-memory storage by patching the trail module."""
    data = {}
    storage = get_storage("file://trail.json")

    monkeypatch.setattr(alerts, "_USER_THRESHOLDS", {})
    monkeypatch.setattr(alerts, "_PUSH_SUBSCRIPTIONS", {})

    def load():
        return data

    def save(new_data):
        data.update(new_data)

    monkeypatch.setattr(storage, "load", load)
    monkeypatch.setattr(storage, "save", save)
    monkeypatch.setattr(trail, "_TRAIL_STORAGE", storage)
    monkeypatch.setattr(trail, "_DATA", {})
    return data


def _daily_ids(response):
    return [task["id"] for task in response["tasks"] if task["type"] == "daily"]


def _once_ids(response):
    return [task["id"] for task in response["tasks"] if task["type"] == "once"]


def test_get_tasks_returns_defaults(memory_storage):
    response = trail.get_tasks("demo")
    tasks = response["tasks"]
    static_ids = [task.id for task in trail.STATIC_DAILY_TASKS]
    assert [t["id"] for t in tasks[: len(static_ids)]] == static_ids
    assert all(not t["completed"] for t in tasks)
    assert response["xp"] == 0
    assert response["streak"] == 0
    daily_ids = _daily_ids(response)
    for static_id in static_ids:
        assert static_id in daily_ids
    assert "demo_allowance_isa" in daily_ids
    assert "demo_allowance_pension" in daily_ids
    assert response["daily_totals"][response["today"]]["completed"] == 0
    assert response["daily_totals"][response["today"]]["total"] == len(daily_ids)

    stored = memory_storage["demo"]
    assert stored["xp"] == 0
    assert stored["streak"] == 0
    assert stored["daily_totals"][response["today"]]["completed"] == 0
    assert stored["daily_totals"][response["today"]]["total"] == len(daily_ids)

    once_ids = _once_ids(response)
    assert once_ids == [
        "create_goal",
        "enable_push_notifications",
        "set_alert_threshold",
    ]


def test_get_tasks_includes_static_tasks_without_data(memory_storage, monkeypatch):
    static_ids = [task.id for task in trail.STATIC_DAILY_TASKS]
    monkeypatch.setattr(trail, "_owners_for_user", lambda user: [])

    response = trail.get_tasks("demo")
    daily_ids = _daily_ids(response)

    assert daily_ids == static_ids
    assert response["daily_totals"][response["today"]]["total"] == len(static_ids)


def test_get_tasks_upgrades_legacy_records(memory_storage):
    today = date.today().isoformat()
    memory_storage["demo"] = {"once": [], "daily": {}}
    trail._DATA["demo"] = memory_storage["demo"]

    response = trail.get_tasks("demo")
    daily_ids = _daily_ids(response)

    assert response["xp"] == 0
    assert response["streak"] == 0
    assert response["daily_totals"][today]["completed"] == 0
    assert response["daily_totals"][today]["total"] == len(daily_ids)

    stored = memory_storage["demo"]
    assert stored["xp"] == 0
    assert stored["streak"] == 0
    assert stored["daily_totals"][today]["completed"] == 0
    assert stored["daily_totals"][today]["total"] == len(daily_ids)


def test_get_tasks_with_completions(memory_storage):
    today = date.today().isoformat()
    baseline = trail.get_tasks("demo")
    daily_ids = _daily_ids(baseline)
    once_ids = _once_ids(baseline)
    assert daily_ids and once_ids

    memory_storage["demo"] = {
        "once": [once_ids[0]],
        "daily": {today: [daily_ids[0]]},
        "xp": trail.DAILY_XP_REWARD,
        "streak": 2,
        "last_completed_day": today,
        "daily_totals": {today: {"completed": 1, "total": len(daily_ids)}},
    }
    trail._DATA["demo"] = memory_storage["demo"]

    response = trail.get_tasks("demo")
    completed = {task["id"]: task["completed"] for task in response["tasks"]}
    assert completed[once_ids[0]] is True
    assert completed[daily_ids[0]] is True
    for task_id in set(_daily_ids(response) + _once_ids(response)) - {daily_ids[0], once_ids[0]}:
        assert completed[task_id] is False
    assert response["xp"] == trail.DAILY_XP_REWARD
    assert response["streak"] == 2
    assert response["daily_totals"][response["today"]]["completed"] == 1
    assert response["daily_totals"][response["today"]]["total"] == len(daily_ids)


def test_mark_complete_records_once_and_daily(memory_storage):
    user = "demo"
    today = date.today().isoformat()

    available = trail.get_tasks(user)
    daily_task = _daily_ids(available)[0]
    once_task = _once_ids(available)[0]

    result = trail.mark_complete(user, daily_task)
    assert memory_storage[user]["daily"][today] == [daily_task]
    assert result["xp"] == trail.DAILY_XP_REWARD
    assert result["daily_totals"][today]["completed"] == 1
    assert result["daily_totals"][today]["total"] == len(_daily_ids(result))
    assert memory_storage[user]["daily_totals"][today]["completed"] == 1
    assert memory_storage[user]["daily_totals"][today]["total"] == len(_daily_ids(result))

    result = trail.mark_complete(user, daily_task)
    assert memory_storage[user]["daily"][today] == [daily_task]
    assert result["xp"] == trail.DAILY_XP_REWARD

    result = trail.mark_complete(user, once_task)
    assert memory_storage[user]["once"] == [once_task]
    assert result["xp"] == trail.DAILY_XP_REWARD + trail.ONCE_XP_REWARD
    assert memory_storage[user]["xp"] == trail.DAILY_XP_REWARD + trail.ONCE_XP_REWARD
    assert memory_storage[user]["daily_totals"][today]["total"] == len(_daily_ids(result))

    result = trail.mark_complete(user, once_task)
    assert memory_storage[user]["once"] == [once_task]
    assert result["xp"] == trail.DAILY_XP_REWARD + trail.ONCE_XP_REWARD

    with pytest.raises(KeyError):
        trail.mark_complete(user, "unknown")


def test_mark_complete_updates_streak(memory_storage):
    user = "demo"
    today = date.today()
    today_str = today.isoformat()
    yesterday = (today - timedelta(days=1)).isoformat()

    baseline = trail.get_tasks(user)
    daily_ids = _daily_ids(baseline)
    assert daily_ids

    memory_storage[user] = {
        "once": [],
        "daily": {yesterday: daily_ids},
        "xp": len(daily_ids) * trail.DAILY_XP_REWARD,
        "streak": 1,
        "last_completed_day": yesterday,
        "daily_totals": {
            yesterday: {
                "completed": len(daily_ids),
                "total": len(daily_ids),
            }
        },
    }
    trail._DATA[user] = memory_storage[user]

    for task_id in daily_ids:
        response = trail.mark_complete(user, task_id)

    assert response["streak"] == 2
    assert response["xp"] == len(daily_ids) * trail.DAILY_XP_REWARD * 2
    assert response["daily_totals"][today_str]["completed"] == len(daily_ids)
    assert response["daily_totals"][today_str]["total"] == len(daily_ids)
    assert memory_storage[user]["streak"] == 2
    assert memory_storage[user]["daily_totals"][today_str]["completed"] == len(daily_ids)


def test_threshold_once_task_ignores_seeded_default(memory_storage, monkeypatch):
    monkeypatch.setattr(alerts, "_USER_THRESHOLDS", {"demo": 5})

    response = trail.get_tasks("demo")
    threshold_task = next(
        task for task in response["tasks"] if task["id"] == "set_alert_threshold"
    )

    assert threshold_task["completed"] is False


def test_threshold_once_task_marks_custom_value(memory_storage, monkeypatch):
    monkeypatch.setattr(alerts, "_USER_THRESHOLDS", {"demo": 10})

    response = trail.get_tasks("demo")
    threshold_task = next(
        task for task in response["tasks"] if task["id"] == "set_alert_threshold"
    )

    assert threshold_task["completed"] is True


def test_threshold_once_task_handles_percent_strings(memory_storage, monkeypatch):
    monkeypatch.setattr(alerts, "_USER_THRESHOLDS", {"demo": "5%"})

    response = trail.get_tasks("demo")
    threshold_task = next(
        task for task in response["tasks"] if task["id"] == "set_alert_threshold"
    )

    assert threshold_task["completed"] is False
