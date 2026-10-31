"""Tests for goal helpers."""

import copy
from datetime import date, timedelta

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


@pytest.mark.parametrize("amount", [float("inf"), float("-inf"), float("nan")])
def test_record_goal_amount_rejects_non_finite(history_storage, amount):
    with pytest.raises(ValueError):
        goals_mod.record_goal_amount("alice", "Car", amount, date(2026, 1, 1))
    assert history_storage.load() == {}


def test_record_goal_amount_rejects_future_dates(history_storage):
    with pytest.raises(ValueError):
        goals_mod.record_goal_amount("alice", "Car", 10.0, date.today() + timedelta(days=1))
    assert history_storage.load() == {}
    # Today itself is fine.
    assert goals_mod.record_goal_amount("alice", "Car", 10.0, date.today()) == [(date.today(), 10.0)]


def test_load_goal_history_skips_future_dated_stored_points(history_storage):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    history_storage.save({"alice": {"Car": [{"date": "2026-01-01", "amount": 10}, {"date": tomorrow, "amount": 99}]}})
    assert goals_mod.load_goal_history("alice", "Car") == [(date(2026, 1, 1), 10.0)]


def test_load_goal_history_skips_non_finite_stored_amounts(history_storage):
    history_storage.save({"alice": {"Car": [{"date": "2026-01-01", "amount": float("inf")}]}})
    assert goals_mod.load_goal_history("alice", "Car") == []


def test_rename_and_delete_goal_history(goal_storage, history_storage):
    goals_mod.record_goal_amount("alice", "Car", 10.0, date(2026, 1, 1))
    goals_mod.rename_goal_history("alice", "Car", "Van")
    assert goals_mod.load_goal_history("alice", "Car") == []
    assert goals_mod.load_goal_history("alice", "Van") == [(date(2026, 1, 1), 10.0)]

    goals_mod.save_goals("alice", [goals_mod.Goal("Van", 100.0, date(2030, 1, 1))])
    goals_mod.delete_goal("alice", "Van")
    assert goals_mod.load_goal_history("alice", "Van") == []


def test_rename_goal_history_refuses_to_overwrite_existing_history(history_storage):
    goals_mod.record_goal_amount("alice", "Car", 10.0, date(2026, 1, 1))
    goals_mod.record_goal_amount("alice", "Van", 20.0, date(2026, 2, 1))

    with pytest.raises(goals_mod.GoalHistoryConflict):
        goals_mod.rename_goal_history("alice", "Car", "Van")

    assert goals_mod.load_goal_history("alice", "Car") == [(date(2026, 1, 1), 10.0)]
    assert goals_mod.load_goal_history("alice", "Van") == [(date(2026, 2, 1), 20.0)]


def test_rename_goal_history_allows_empty_destination(history_storage):
    history_storage.save({"alice": {"Car": [{"date": "2026-01-01", "amount": 10}], "Van": []}})
    goals_mod.rename_goal_history("alice", "Car", "Van")
    assert goals_mod.load_goal_history("alice", "Van") == [(date(2026, 1, 1), 10.0)]


def test_history_helpers_do_not_write_when_nothing_changes(history_storage, monkeypatch):
    def fail_save(data):  # pragma: no cover - safety guard
        pytest.fail("history should not be saved")

    monkeypatch.setattr(history_storage, "save", fail_save)
    goals_mod.rename_goal_history("alice", "Missing", "Other")
    goals_mod.delete_goal_history("alice", "Missing")


def test_record_goal_amount_interleaved_writes_lose_earlier_snapshot(history_storage, monkeypatch):
    """Pin the accepted lost-update risk documented in ``_record_progress`` (#11186).

    Request A reads the store, request B then records a snapshot (for another
    user, since the store is one shared document), and A writes back what it
    read. B's snapshot is silently lost: there is no version check.
    """
    goals_mod.record_goal_amount("alice", "Car", 10.0, date(2026, 1, 1))
    stale = history_storage.load()  # what request A read before B wrote

    goals_mod.record_goal_amount("bob", "Van", 99.0, date(2026, 1, 2))  # request B
    assert goals_mod.load_goal_history("bob", "Van") == [(date(2026, 1, 2), 99.0)]

    real_load = history_storage.load
    monkeypatch.setattr(history_storage, "load", lambda: copy.deepcopy(stale))
    points = goals_mod.record_goal_amount("alice", "Car", 20.0, date(2026, 1, 3))  # request A
    monkeypatch.setattr(history_storage, "load", real_load)

    # A's own response includes its snapshot and the stored history matches it...
    assert points == [(date(2026, 1, 1), 10.0), (date(2026, 1, 3), 20.0)]
    assert goals_mod.load_goal_history("alice", "Car") == points
    # ...but B's earlier write was overwritten.
    assert goals_mod.load_goal_history("bob", "Van") == []
