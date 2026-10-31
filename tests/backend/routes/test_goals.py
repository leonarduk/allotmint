import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import backend.routes.goals as goals


class FakeGoal:
    def __init__(self, name: str, target_amount: float, target_date: datetime.date):
        self.name = name
        self.target_amount = target_amount
        self.target_date = target_date

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "target_amount": self.target_amount,
            "target_date": self.target_date,
        }

    def progress(self, current_amount: float) -> float:
        return current_amount / self.target_amount if self.target_amount else 0.0


@pytest.fixture
def fake_goal_class(monkeypatch):
    monkeypatch.setattr(goals, "Goal", FakeGoal)
    return FakeGoal


def test_create_goal_uses_payload_and_returns_dict(monkeypatch, fake_goal_class):
    payload = goals.GoalPayload(
        name="Retirement",
        target_amount=1000.0,
        target_date=datetime.date(2030, 1, 1),
    )
    added = SimpleNamespace(owner=None, goal=None)

    def fake_add_goal(owner: str, goal):
        added.owner = owner
        added.goal = goal

    monkeypatch.setattr(goals, "add_goal", fake_add_goal)

    result = goals._create_goal("demo-owner", payload)

    assert isinstance(added.goal, fake_goal_class)
    assert added.owner == "demo-owner"
    assert added.goal.name == payload.name
    assert added.goal.target_amount == payload.target_amount
    assert added.goal.target_date == payload.target_date
    assert result == goals.GoalPayload(**added.goal.to_dict())


def test_list_goals_returns_payloads(monkeypatch, fake_goal_class):
    goal_one = fake_goal_class("Trip", 1500.0, datetime.date(2029, 7, 1))
    goal_two = fake_goal_class("Car", 10000.0, datetime.date(2032, 12, 31))

    monkeypatch.setattr(goals, "load_goals", lambda owner: [goal_one, goal_two])

    payloads = goals._list_goals("demo-owner")

    assert payloads == [goals.GoalPayload(**goal_one.to_dict()), goals.GoalPayload(**goal_two.to_dict())]


def test_get_goal_returns_progress_and_trades(monkeypatch, fake_goal_class):
    fake = fake_goal_class("Emergency", 2000.0, datetime.date(2030, 6, 30))

    monkeypatch.setattr(goals, "load_goals", lambda owner: [fake])
    monkeypatch.setattr(goals, "load_goal_history", lambda owner, name: [])

    expected_trades = [{"symbol": "goal", "action": "buy", "amount": 100.0}]

    def fake_suggest_trades(actual, target):
        return expected_trades

    monkeypatch.setattr(goals, "suggest_trades", fake_suggest_trades)

    response = goals._get_goal("owner", "Emergency", current_amount=500.0)

    assert response.progress == pytest.approx(0.25)
    assert response.trades == expected_trades
    assert response.current_amount == 500.0
    assert response.projection["status"] == "insufficient_history"
    assert response.model_dump(exclude={"progress", "trades", "current_amount", "projection"}) == fake.to_dict()


def test_get_goal_without_amount_or_history_leaves_progress_unknown(monkeypatch, fake_goal_class):
    fake = fake_goal_class("Emergency", 2000.0, datetime.date(2030, 6, 30))
    monkeypatch.setattr(goals, "load_goals", lambda owner: [fake])
    monkeypatch.setattr(goals, "load_goal_history", lambda owner, name: [])

    response = goals._get_goal("owner", "Emergency")

    # Unknown is not the same as zero (#7829).
    assert response.progress is None
    assert response.current_amount is None
    assert response.trades is None
    assert response.projection["status"] == "insufficient_history"


def test_get_goal_falls_back_to_latest_recorded_amount_and_projects(monkeypatch, fake_goal_class):
    fake = fake_goal_class("Emergency", 2000.0, datetime.date(2030, 6, 30))
    history = [(datetime.date(2026, 1, 1), 200.0), (datetime.date(2026, 3, 2), 500.0)]
    monkeypatch.setattr(goals, "load_goals", lambda owner: [fake])
    monkeypatch.setattr(goals, "load_goal_history", lambda owner, name: history)

    response = goals._get_goal("owner", "Emergency")

    assert response.current_amount == 500.0
    assert response.progress == pytest.approx(0.25)
    assert response.projection["status"] == "projected"
    assert response.projection["projected_date"] == "2026-12-27"
    assert response.projection["on_track"] is True


def test_record_progress_stores_snapshot_and_returns_detail(monkeypatch, fake_goal_class):
    fake = fake_goal_class("Emergency", 2000.0, datetime.date(2030, 6, 30))
    monkeypatch.setattr(goals, "load_goals", lambda owner: [fake])
    recorded = []

    def fake_record(owner, name, amount, on):
        recorded.append((owner, name, amount, on))
        return [(on, amount)]

    monkeypatch.setattr(goals, "record_goal_amount", fake_record)

    payload = goals.ProgressPayload(amount=800.0, on=datetime.date(2026, 5, 1))
    response = goals._record_progress("owner", "Emergency", payload)

    assert recorded == [("owner", "Emergency", 800.0, datetime.date(2026, 5, 1))]
    assert response.progress == pytest.approx(0.4)
    assert response.projection["status"] == "insufficient_history"
    assert response.projection["points"] == 1


def test_record_progress_missing_goal_raises_404(monkeypatch):
    monkeypatch.setattr(goals, "load_goals", lambda owner: [])

    with pytest.raises(HTTPException) as exc:
        goals._record_progress("owner", "Missing", goals.ProgressPayload(amount=1.0))

    assert exc.value.status_code == 404


def test_get_goal_missing_raises_404(monkeypatch):
    monkeypatch.setattr(goals, "load_goals", lambda owner: [])

    with pytest.raises(HTTPException) as exc:
        goals._get_goal("owner", "Missing", current_amount=100.0)

    assert exc.value.status_code == 404


def test_update_goal_replaces_goal_and_saves(monkeypatch, fake_goal_class):
    existing = fake_goal_class("Old", 3000.0, datetime.date(2030, 12, 31))
    saved = SimpleNamespace(owner=None, goals=None)

    monkeypatch.setattr(goals, "load_goals", lambda owner: [existing])

    def fake_save_goals(owner: str, goals_list):
        saved.owner = owner
        saved.goals = goals_list

    monkeypatch.setattr(goals, "save_goals", fake_save_goals)
    renamed = []
    monkeypatch.setattr(goals, "rename_goal_history", lambda owner, old, new: renamed.append((owner, old, new)))

    payload = goals.GoalPayload(
        name="Updated",
        target_amount=3500.0,
        target_date=datetime.date(2031, 1, 1),
    )

    result = goals._update_goal("demo-owner", "Old", payload)

    assert saved.owner == "demo-owner"
    assert len(saved.goals) == 1
    saved_goal = saved.goals[0]
    assert isinstance(saved_goal, fake_goal_class)
    assert saved_goal.name == payload.name
    assert saved_goal.target_amount == payload.target_amount
    assert saved_goal.target_date == payload.target_date
    assert result == payload
    assert renamed == [("demo-owner", "Old", "Updated")]


def test_update_goal_moves_history_back_when_save_fails(monkeypatch, fake_goal_class):
    existing = fake_goal_class("Old", 3000.0, datetime.date(2030, 12, 31))
    monkeypatch.setattr(goals, "load_goals", lambda owner: [existing])
    renamed = []
    monkeypatch.setattr(goals, "rename_goal_history", lambda owner, old, new: renamed.append((old, new)))

    def failing_save(owner, goals_list):
        raise OSError("disk full")

    monkeypatch.setattr(goals, "save_goals", failing_save)
    payload = goals.GoalPayload(name="New", target_amount=1.0, target_date=datetime.date(2031, 1, 1))

    with pytest.raises(OSError):
        goals._update_goal("demo-owner", "Old", payload)

    # History moved first, then restored, so it still matches the unsaved goal.
    assert renamed == [("Old", "New"), ("New", "Old")]


def test_update_goal_history_conflict_becomes_409_without_saving(monkeypatch, fake_goal_class):
    existing = fake_goal_class("Old", 3000.0, datetime.date(2030, 12, 31))
    monkeypatch.setattr(goals, "load_goals", lambda owner: [existing])

    def conflicting_rename(owner, old, new):
        raise goals.GoalHistoryConflict("taken")

    def fail_save(owner, goals_list):  # pragma: no cover - safety guard
        pytest.fail("goal should not be saved")

    monkeypatch.setattr(goals, "rename_goal_history", conflicting_rename)
    monkeypatch.setattr(goals, "save_goals", fail_save)
    payload = goals.GoalPayload(name="New", target_amount=1.0, target_date=datetime.date(2031, 1, 1))

    with pytest.raises(HTTPException) as exc:
        goals._update_goal("demo-owner", "Old", payload)

    assert exc.value.status_code == 409


def test_update_goal_missing_raises_404(monkeypatch):
    monkeypatch.setattr(goals, "load_goals", lambda owner: [])

    payload = goals.GoalPayload(
        name="Updated",
        target_amount=3500.0,
        target_date=datetime.date(2031, 1, 1),
    )

    with pytest.raises(HTTPException) as exc:
        goals._update_goal("demo-owner", "Unknown", payload)

    assert exc.value.status_code == 404


def test_remove_goal_deletes_when_present(monkeypatch):
    existing = FakeGoal("Keep", 4000.0, datetime.date(2032, 1, 1))

    monkeypatch.setattr(goals, "load_goals", lambda owner: [existing])
    deleted = SimpleNamespace(owner=None, name=None)

    def fake_delete_goal(owner: str, name: str):
        deleted.owner = owner
        deleted.name = name

    monkeypatch.setattr(goals, "delete_goal", fake_delete_goal)

    response = goals._remove_goal("demo-owner", "Keep")

    assert deleted.owner == "demo-owner"
    assert deleted.name == "Keep"
    assert response == {"status": "deleted"}


def test_remove_goal_missing_raises_404(monkeypatch):
    monkeypatch.setattr(goals, "load_goals", lambda owner: [])

    with pytest.raises(HTTPException) as exc:
        goals._remove_goal("demo-owner", "Missing")

    assert exc.value.status_code == 404
