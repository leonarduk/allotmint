from datetime import date, timedelta

import pytest

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
    summary = trail.get_tasks("alice")
    assert [t["id"] for t in summary["tasks"]] == [
        t["id"] for t in trail.DEFAULT_TASKS
    ]
    assert all(not t["completed"] for t in summary["tasks"])
    assert summary["xp"] == 0
    assert summary["streak"] == 0
    assert summary["daily_totals"] == {}


def test_get_tasks_with_completions(memory_storage):
    today = date.today().isoformat()
    memory_storage["bob"] = {"once": ["create_goal"], "daily": {today: ["check_market"]}}
    summary = trail.get_tasks("bob")
    completed = {t["id"]: t["completed"] for t in summary["tasks"]}
    assert completed["create_goal"] is True
    assert completed["check_market"] is True
    for task in trail.DEFAULT_TASKS:
        if task["id"] not in {"create_goal", "check_market"}:
            assert completed[task["id"]] is False
    assert summary["xp"] == 0
    assert summary["streak"] == 0
    assert summary["daily_totals"] == {}


class FakeDate(date):
    """Helper date subclass to control ``today`` in tests."""

    today_value = date.today()

    @classmethod
    def today(cls):  # type: ignore[override]
        return cls.today_value


def test_mark_complete_records_once_and_daily(memory_storage, monkeypatch):
    user = "carol"
    monkeypatch.setattr(trail, "date", FakeDate)

    daily_ids = [t["id"] for t in trail.DEFAULT_TASKS if t["type"] == "daily"]
    once_id = next(t["id"] for t in trail.DEFAULT_TASKS if t["type"] == "once")

    FakeDate.today_value = date(2024, 1, 1)
    today = FakeDate.today_value.isoformat()

    summary = trail.mark_complete(user, daily_ids[0])
    assert summary["xp"] == trail.XP_PER_COMPLETION
    assert summary["streak"] == 0
    assert summary["daily_totals"][today] == 1

    summary = trail.mark_complete(user, daily_ids[1])
    assert summary["xp"] == trail.XP_PER_COMPLETION * 2
    assert summary["streak"] == 1
    assert summary["daily_totals"][today] == 2

    summary = trail.mark_complete(user, once_id)
    assert summary["xp"] == trail.XP_PER_COMPLETION * 3

    summary = trail.mark_complete(user, daily_ids[1])
    assert summary["xp"] == trail.XP_PER_COMPLETION * 3
    assert summary["daily_totals"][today] == 2

    FakeDate.today_value = FakeDate.today_value + timedelta(days=1)
    next_day = FakeDate.today_value.isoformat()

    summary = trail.mark_complete(user, daily_ids[0])
    assert summary["streak"] == 1
    assert summary["daily_totals"][next_day] == 1

    summary = trail.mark_complete(user, daily_ids[1])
    assert summary["streak"] == 2
    assert summary["daily_totals"][next_day] == 2

    with pytest.raises(KeyError):
        trail.mark_complete(user, "unknown")
