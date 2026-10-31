"""Tests for goal helpers."""

from datetime import date

import pytest

from backend.common import goals as goals_mod
from backend.common.storage import get_storage


@pytest.fixture
def goal_storage(tmp_path, monkeypatch):
    storage = get_storage(f"file://{tmp_path / 'goals.json'}")
    storage.save({})
    monkeypatch.setattr(goals_mod, "_STORAGE", storage)
    return storage


def test_goal_to_from_dict_roundtrip():
    goal = goals_mod.Goal("Car", 5000.0, date(2025, 1, 1))
    data = goal.to_dict()
    assert data == {
        "name": "Car",
        "target_amount": 5000.0,
        "target_date": "2025-01-01",
    }
    assert goals_mod.Goal.from_dict(data) == goal


def test_goal_progress():
    goal = goals_mod.Goal("Holiday", 1000.0, date(2024, 1, 1))
    assert goal.progress(0) == 0.0
    assert goal.progress(500) == 0.5
    assert goal.progress(1200) == 1.0  # over target

    zero_goal = goals_mod.Goal("Zero", 0.0, date(2024, 1, 1))
    assert zero_goal.progress(100) == 0.0


def test_save_and_load_goals(goal_storage):
    goal = goals_mod.Goal("Car", 5000.0, date(2025, 1, 1))
    goals_mod.save_goals("alice", [goal])
    assert goals_mod.load_goals("alice") == [goal]


def test_add_goal(goal_storage):
    goal = goals_mod.Goal("Trip", 2000.0, date(2024, 6, 1))
    goals_mod.add_goal("alice", goal)
    assert goals_mod.load_goals("alice") == [goal]


def test_delete_goal(goal_storage):
    g1 = goals_mod.Goal("A", 100.0, date(2024, 1, 1))
    g2 = goals_mod.Goal("B", 200.0, date(2024, 1, 1))
    goals_mod.save_goals("alice", [g1, g2])
    goals_mod.delete_goal("alice", "A")
    assert goals_mod.load_goals("alice") == [g2]


def test_load_goals_ignores_malformed_entries(goal_storage):
    goal_storage.save(
        {
            "alice": [
                {"name": "House", "target_amount": 3000, "target_date": "2025-01-01"},
                {"name": "Bad", "target_amount": "oops", "target_date": "not-a-date"},
                "not a dict",
            ]
        }
    )
    result = goals_mod.load_goals("alice")
    assert len(result) == 1
    assert result[0].name == "House"


def test_load_all_goals_ignores_malformed_entries(goal_storage):
    g1 = goals_mod.Goal("House", 3000.0, date(2025, 1, 1))
    g2 = goals_mod.Goal("Trip", 2000.0, date(2024, 6, 1))
    goal_storage.save(
        {
            "alice": [
                g1.to_dict(),
                {"name": "Bad", "target_amount": "oops", "target_date": "not"},
            ],
            "bob": ["not a dict", g2.to_dict()],
        }
    )
    result = goals_mod.load_all_goals()
    assert result == {"alice": [g1], "bob": [g2]}


@pytest.fixture
def history_storage(tmp_path, monkeypatch):
    storage = get_storage(f"file://{tmp_path / 'goal_history.json'}")
    storage.save({})
    monkeypatch.setattr(goals_mod, "_HISTORY_STORAGE", storage)
    return storage


def test_record_goal_amount_keeps_one_snapshot_per_day(history_storage):
    goals_mod.record_goal_amount("alice", "Car", 100.0, date(2026, 2, 1))
    goals_mod.record_goal_amount("alice", "Car", 50.0, date(2026, 1, 1))
    points = goals_mod.record_goal_amount("alice", "Car", 120.0, date(2026, 2, 1))
    assert points == [(date(2026, 1, 1), 50.0), (date(2026, 2, 1), 120.0)]
    assert goals_mod.load_goal_history("alice", "Car") == points
    assert goals_mod.load_goal_history("bob", "Car") == []


def test_load_goal_history_ignores_malformed_entries(history_storage):
    history_storage.save(
        {
            "alice": {"Car": [{"date": "2026-01-01", "amount": 10}, {"date": "bad", "amount": 1}, {"amount": 2}]},
            "bob": "not a dict",
        }
    )
    assert goals_mod.load_goal_history("alice", "Car") == [(date(2026, 1, 1), 10.0)]
    assert goals_mod.load_goal_history("bob", "Car") == []


def test_rename_and_delete_goal_history(goal_storage, history_storage):
    goals_mod.record_goal_amount("alice", "Car", 10.0, date(2026, 1, 1))
    goals_mod.rename_goal_history("alice", "Car", "Van")
    assert goals_mod.load_goal_history("alice", "Car") == []
    assert goals_mod.load_goal_history("alice", "Van") == [(date(2026, 1, 1), 10.0)]

    goals_mod.save_goals("alice", [goals_mod.Goal("Van", 100.0, date(2030, 1, 1))])
    goals_mod.delete_goal("alice", "Van")
    assert goals_mod.load_goal_history("alice", "Van") == []


def test_history_helpers_do_not_write_when_nothing_changes(history_storage, monkeypatch):
    def fail_save(data):  # pragma: no cover - safety guard
        pytest.fail("history should not be saved")

    monkeypatch.setattr(history_storage, "save", fail_save)
    goals_mod.rename_goal_history("alice", "Missing", "Other")
    goals_mod.delete_goal_history("alice", "Missing")
