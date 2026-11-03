from __future__ import annotations

"""Goal tracking helpers."""

import math
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from backend.common.conditional_store import PreconditionFailed
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


def _load_document(storage: JSONStorage, *, for_write: bool) -> object:
    """The stored document; with ``for_write``, a failed read raises instead of reading as empty.

    ``load()`` reads any S3 error (throttling, 5xx, AccessDenied) as ``{}``.
    Both stores hold every owner's data in one document, so writing a change
    on top of that ``{}`` would wipe everyone else's (#11299). Writers
    therefore use ``S3JSONStorage.load_existing``, as plans and the decision
    journal do (#11159): ``None`` only for a missing key, any other error
    raises. File and SSM backends have no ``load_existing`` and keep ``load()``.
    """
    load_existing = getattr(storage, "load_existing", None) if for_write else None
    if load_existing is None:
        return storage.load()
    data = load_existing()
    return {} if data is None else data


def _load_raw(*, for_write: bool = False) -> Dict[str, List[Dict[str, object]]]:
    data = _load_document(_STORAGE, for_write=for_write)
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, list)}


def _save_raw(data: Dict[str, List[Dict[str, object]]]) -> None:
    _STORAGE.save(data)


def _parse_goals(raw: List[Dict[str, object]]) -> List[Goal]:
    goals: List[Goal] = []
    for g in raw:
        try:
            goals.append(Goal.from_dict(g))
        except Exception:
            continue
    return goals


def load_goals(user: str) -> List[Goal]:
    return _parse_goals(_load_raw().get(user, []))


def _load_goals_for_write(user: str) -> List[Goal]:
    return _parse_goals(_load_raw(for_write=True).get(user, []))


def save_goals(user: str, goals: List[Goal]) -> None:
    data = _load_raw(for_write=True)
    data[user] = [g.to_dict() for g in goals]
    _save_raw(data)


def add_goal(user: str, goal: Goal) -> None:
    goals = _load_goals_for_write(user)
    goals = [g for g in goals if g.name != goal.name]
    goals.append(goal)
    save_goals(user, goals)


def delete_goal(user: str, name: str) -> None:
    goals = [g for g in _load_goals_for_write(user) if g.name != name]
    save_goals(user, goals)
    delete_goal_history(user, name)


# progress history ------------------------------------------------------------


_HistoryDoc = Dict[str, Dict[str, List[Dict[str, object]]]]

# Conditional history writes (#11291): how many read-modify-write rounds one
# request makes before reporting a conflict. Each lost round means another
# request wrote in between, so a small bound is plenty for hand-entered progress.
_HISTORY_WRITE_ATTEMPTS = 4


class GoalHistoryWriteConflict(Exception):
    """Concurrent writes kept invalidating a conditional history save (#11291)."""


def _history_doc(data: object) -> _HistoryDoc:
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _load_history_raw(*, for_write: bool = False) -> _HistoryDoc:
    return _history_doc(_load_document(_HISTORY_STORAGE, for_write=for_write))


def _update_history(mutate: Callable[[_HistoryDoc], bool]) -> None:
    """Read the history store, apply ``mutate`` and write it back if it returns ``True``.

    On a store with conditional writes (``S3JSONStorage``: ``load_versioned``
    / ``save_if_match``) the write only lands if the document's ETag is still
    the one read, so a concurrent writer's snapshot is never overwritten; a
    lost race re-reads and re-applies ``mutate``, up to
    ``_HISTORY_WRITE_ATTEMPTS`` rounds, then raises
    :class:`GoalHistoryWriteConflict`. ``mutate`` must therefore be safe to run
    again on a fresh read. The file and SSM stores have no conditional write,
    so they keep the plain read-modify-write and its lost-update risk (see
    ``backend.routes.goals._record_progress``).
    """
    load_versioned = getattr(_HISTORY_STORAGE, "load_versioned", None)
    save_if_match = getattr(_HISTORY_STORAGE, "save_if_match", None)
    if load_versioned is None or save_if_match is None:
        data = _load_history_raw(for_write=True)
        if mutate(data):
            _HISTORY_STORAGE.save(data)
        return
    for _ in range(_HISTORY_WRITE_ATTEMPTS):
        raw, etag = load_versioned()
        data = _history_doc({} if raw is None else raw)
        if not mutate(data):
            return
        try:
            save_if_match(data, etag)
        except PreconditionFailed:
            continue
        return
    raise GoalHistoryWriteConflict(
        f"Goal history changed concurrently; gave up after {_HISTORY_WRITE_ATTEMPTS} attempts"
    )


def load_goal_history(user: str, name: str) -> List[Tuple[date, float]]:
    """Return ``(date, amount)`` snapshots for a goal, oldest first.

    Malformed, non-finite and future-dated entries are skipped.
    """
    return _parse_history(_load_history_raw().get(user, {}).get(name, []))


def _parse_history(raw: object) -> List[Tuple[date, float]]:
    points: List[Tuple[date, float]] = []
    today = date.today()
    for entry in raw if isinstance(raw, list) else []:
        try:
            amount = float(entry["amount"])
            on = date.fromisoformat(str(entry["date"]))
            if math.isfinite(amount) and on <= today:
                points.append((on, amount))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(points)


def record_goal_amount(user: str, name: str, amount: float, on: date) -> List[Tuple[date, float]]:
    """Record the amount saved toward a goal on ``on`` (one snapshot per day).

    Returns the goal's updated history. Raises ``ValueError`` for a non-finite
    amount, which would otherwise be stored as non-standard JSON, or for a
    date after today.

    The whole store is read, modified and written back through
    :func:`_update_history`: a conditional write with bounded retry on S3
    (raising :class:`GoalHistoryWriteConflict` when every attempt loses a
    race), a plain write on the file/SSM stores (#11291).
    """
    if not math.isfinite(amount):
        raise ValueError("Goal amount must be a finite number")
    if on > date.today():
        raise ValueError("Goal progress cannot be recorded for a future date")
    points: List[Tuple[date, float]] = []

    def add_snapshot(data: _HistoryDoc) -> bool:
        by_day = dict(_parse_history(data.get(user, {}).get(name, [])))
        by_day[on] = float(amount)
        points[:] = sorted(by_day.items())
        data.setdefault(user, {})[name] = [{"date": d.isoformat(), "amount": a} for d, a in points]
        return True

    _update_history(add_snapshot)
    return points


class GoalHistoryConflict(ValueError):
    """Raised when moving history would overwrite another goal's history."""


def rename_goal_history(user: str, old: str, new: str) -> None:
    """Move a goal's history to its new name; a no-op when there is none.

    Raises :class:`GoalHistoryConflict` rather than overwrite a non-empty
    history already stored under ``new``.
    """

    def move(data: _HistoryDoc) -> bool:
        user_history = data.get(user, {})
        if old == new or old not in user_history:
            return False
        if user_history.get(new):
            raise GoalHistoryConflict(f"History already exists for goal {new!r}")
        user_history[new] = user_history.pop(old)
        return True

    _update_history(move)


def delete_goal_history(user: str, name: str) -> None:
    """Drop a goal's history; a no-op when there is none."""

    def drop(data: _HistoryDoc) -> bool:
        if name not in data.get(user, {}):
            return False
        del data[user][name]
        return True

    _update_history(drop)


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
    "GoalHistoryWriteConflict",
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
