from datetime import date

import pytest

from backend.common.storage import get_storage
from backend.common import goals as goals_mod


@pytest.fixture
def goal_storage(tmp_path, monkeypatch):
    storage = get_storage(f"file://{tmp_path / 'goals.json'}")
    storage.save({})
    monkeypatch.setattr(goals_mod, "_STORAGE", storage)
    return storage


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
