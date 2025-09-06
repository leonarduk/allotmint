from __future__ import annotations

"""Goal tracking helpers."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List
import os

from backend.common.storage import get_storage, JSONStorage
from backend.config import config

_DEFAULT_GOALS_URI = (
    f"file://{(config.repo_root or Path(__file__).resolve().parents[1]) / 'data' / 'goals.json'}"
)

try:
    _STORAGE: JSONStorage = get_storage(os.getenv("GOALS_STORAGE_URI", _DEFAULT_GOALS_URI))
except Exception:
    _STORAGE = get_storage(_DEFAULT_GOALS_URI)


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
    "load_goals",
    "save_goals",
    "add_goal",
    "delete_goal",
    "load_all_goals",
]
