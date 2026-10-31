from __future__ import annotations

"""Goal tracking helpers."""

import math
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

from backend.common.storage import JSONStorage, get_storage
from backend.config import config

_DEFAULT_GOALS_URI = f"file://{(config.repo_root or Path(__file__).resolve().parents[1]) / 'data' / 'goals.json'}"

try:
    _STORAGE: JSONStorage = get_storage(os.getenv("GOALS_STORAGE_URI", _DEFAULT_GOALS_URI))
except Exception:
    _STORAGE = get_storage(_DEFAULT_GOALS_URI)

# Recorded "amount saved" snapshots, kept apart from the goal definitions so
# that editing a goal never rewrites its history. Shape:
# ``{user: {goal name: [{"date": "YYYY-MM-DD", "amount": float}, ...]}}``.
_DEFAULT_HISTORY_URI = (
    f"file://{(config.repo_root or Path(__file__).resolve().parents[1]) / 'data' / 'goal_history.json'}"
)

try:
    _HISTORY_STORAGE: JSONStorage = get_storage(os.getenv("GOAL_HISTORY_STORAGE_URI", _DEFAULT_HISTORY_URI))
except Exception:
    _HISTORY_STORAGE = get_storage(_DEFAULT_HISTORY_URI)


@dataclass
class Goal:
    """Simple savings goal."""

    name: str
    target_amount: float
    target_date: date

    def to_dict(self) -> Dict[str, str | float]:
        return {
            "name": self.name,
            "target_amount": self.target_amount,
            "target_date": self.target_date.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "Goal":
        return cls(
            name=str(data.get("name", "")),
            target_amount=float(data.get("target_amount", 0.0)),
            target_date=date.fromisoformat(str(data.get("target_date", "1970-01-01"))),
        )

    def progress(self, current_amount: float) -> float:
        if self.target_amount <= 0:
            return 0.0
        return max(0.0, min(current_amount / self.target_amount, 1.0))


# persistence helpers ---------------------------------------------------------


def _load_raw() -> Dict[str, List[Dict[str, object]]]:
    data = _STORAGE.load()
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, list)}


def _save_raw(data: Dict[str, List[Dict[str, object]]]) -> None:
    _STORAGE.save(data)


def load_goals(user: str) -> List[Goal]:
    raw = _load_raw().get(user, [])
    goals: List[Goal] = []
    for g in raw:
        try:
            goals.append(Goal.from_dict(g))
        except Exception:
            continue
    return goals


def save_goals(user: str, goals: List[Goal]) -> None:
    data = _load_raw()
    data[user] = [g.to_dict() for g in goals]
    _save_raw(data)


def add_goal(user: str, goal: Goal) -> None:
    goals = load_goals(user)
    goals = [g for g in goals if g.name != goal.name]
    goals.append(goal)
    save_goals(user, goals)


def delete_goal(user: str, name: str) -> None:
    goals = [g for g in load_goals(user) if g.name != name]
    save_goals(user, goals)
    delete_goal_history(user, name)


# progress history ------------------------------------------------------------


def _load_history_raw() -> Dict[str, Dict[str, List[Dict[str, object]]]]:
    data = _HISTORY_STORAGE.load()
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def load_goal_history(user: str, name: str) -> List[Tuple[date, float]]:
    """Return ``(date, amount)`` snapshots for a goal, oldest first."""
    raw = _load_history_raw().get(user, {}).get(name, [])
    points: List[Tuple[date, float]] = []
    for entry in raw if isinstance(raw, list) else []:
        try:
            amount = float(entry["amount"])
            if math.isfinite(amount):
                points.append((date.fromisoformat(str(entry["date"])), amount))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(points)


def record_goal_amount(user: str, name: str, amount: float, on: date) -> List[Tuple[date, float]]:
    """Record the amount saved toward a goal on ``on`` (one snapshot per day).

    Returns the goal's updated history. Raises ``ValueError`` for a non-finite
    amount, which would otherwise be stored as non-standard JSON.

    This is a plain read-modify-write of the whole store: it assumes a single
    writer (the app's usage), so concurrent writers could lose an update.
    """
    if not math.isfinite(amount):
        raise ValueError("Goal amount must be a finite number")
    data = _load_history_raw()
    by_day = dict(load_goal_history(user, name))
    by_day[on] = float(amount)
    points = sorted(by_day.items())
    data.setdefault(user, {})[name] = [{"date": d.isoformat(), "amount": a} for d, a in points]
    _HISTORY_STORAGE.save(data)
    return points


class GoalHistoryConflict(ValueError):
    """Raised when moving history would overwrite another goal's history."""


def rename_goal_history(user: str, old: str, new: str) -> None:
    """Move a goal's history to its new name; a no-op when there is none.

    Raises :class:`GoalHistoryConflict` rather than overwrite a non-empty
    history already stored under ``new``.
    """
    data = _load_history_raw()
    user_history = data.get(user, {})
    if old == new or old not in user_history:
        return
    if user_history.get(new):
        raise GoalHistoryConflict(f"History already exists for goal {new!r}")
    user_history[new] = user_history.pop(old)
    _HISTORY_STORAGE.save(data)


def delete_goal_history(user: str, name: str) -> None:
    """Drop a goal's history; a no-op when there is none."""
    data = _load_history_raw()
    if name not in data.get(user, {}):
        return
    del data[user][name]
    _HISTORY_STORAGE.save(data)


def load_all_goals() -> Dict[str, List[Goal]]:
    data = _load_raw()
    out: Dict[str, List[Goal]] = {}
    for user, items in data.items():
        lst: List[Goal] = []
        for g in items:
            try:
                lst.append(Goal.from_dict(g))
            except Exception:
                continue
        out[user] = lst
    return out


__all__ = [
    "Goal",
    "GoalHistoryConflict",
    "load_goals",
    "save_goals",
    "add_goal",
    "delete_goal",
    "load_all_goals",
    "load_goal_history",
    "record_goal_amount",
    "rename_goal_history",
    "delete_goal_history",
]
