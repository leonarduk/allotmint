from __future__ import annotations

"""Simple task tracking for the Trail page.

This module exposes a small set of static tasks split between daily and
one-off items. Completion state is stored in a JSON document using the
``backend.common.storage`` helpers so that tests can use an in-memory file
while deployments may swap in other backends.
"""

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

from backend.common.storage import get_storage
from backend.config import config

# ---------------------------------------------------------------------------
# Task definitions
# ---------------------------------------------------------------------------

Task = Dict[str, str]

DEFAULT_TASKS: List[Task] = [
    {
        "id": "check_market",
        "title": "Check market overview",
        "type": "daily",
        "commentary": "Stay informed about today's movements.",
    },
    {
        "id": "review_portfolio",
        "title": "Review your portfolio",
        "type": "daily",
        "commentary": "Consistency builds good habits.",
    },
    {
        "id": "create_goal",
        "title": "Set up your first goal",
        "type": "once",
        "commentary": "Planning helps you stay on track.",
    },
    {
        "id": "add_watchlist",
        "title": "Add a stock to your watchlist",
        "type": "once",
        "commentary": "Keep an eye on potential investments.",
    },
]

TASK_IDS = {t["id"] for t in DEFAULT_TASKS}
DAILY_TASK_IDS = [t["id"] for t in DEFAULT_TASKS if t["type"] == "daily"]
ONCE_TASK_IDS = [t["id"] for t in DEFAULT_TASKS if t["type"] == "once"]
DAILY_TASK_COUNT = len(DAILY_TASK_IDS)

DAILY_XP_REWARD = 10
ONCE_XP_REWARD = 25

# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

_DEFAULT_TRAIL_URI = (
    f"file://{(config.repo_root or Path(__file__).resolve().parents[1]) / 'data' / 'trail.json'}"
)
_TRAIL_STORAGE = get_storage(os.getenv("TRAIL_URI", _DEFAULT_TRAIL_URI))

# Data format per user::
# {
#   "once": [task_id, ...],
#   "daily": { "YYYY-MM-DD": [task_id, ...] },
#   "xp": int,
#   "streak": int,
#   "last_completed_day": str,
#   "daily_totals": { "YYYY-MM-DD": {"completed": int, "total": int} }
# }
_DATA: Dict[str, Dict] = {}


def _update_daily_totals(user_data: Dict, day: str, *, completed: int | None = None) -> None:
    """Persist the completion totals for ``day``.

    Centralising this logic keeps the ``daily_totals`` payload consistent whether the
    data is being initialised or updated after marking tasks complete.  When
    ``completed`` is omitted the value is derived from the recorded daily tasks.
    """

    if completed is None:
        completed = len(set(user_data["daily"].get(day, [])))

    user_data.setdefault("daily_totals", {})[day] = {
        "completed": completed,
        "total": DAILY_TASK_COUNT,
    }


def _ensure_user_data(user: str, *, persist: bool = False) -> Dict:
    """Ensure the cached state for ``user`` has all expected keys.

    Parameters
    ----------
    user:
        Identifier of the user whose state should be normalised.
    persist:
        When ``True`` the storage layer is updated if new keys are added.
    """

    user_data = _DATA.setdefault(user, {})
    changed = False

    if "once" not in user_data:
        user_data["once"] = []
        changed = True
    if "daily" not in user_data:
        user_data["daily"] = {}
        changed = True
    if "xp" not in user_data:
        user_data["xp"] = 0
        changed = True
    if "streak" not in user_data:
        user_data["streak"] = 0
        changed = True
    if "last_completed_day" not in user_data:
        user_data["last_completed_day"] = ""
        changed = True
    if "daily_totals" not in user_data:
        user_data["daily_totals"] = {}
        changed = True

    if persist and changed:
        _save()

    return user_data


def _load() -> None:
    """Load in-memory cache from storage."""
    global _DATA
    if _DATA:
        return
    try:
        data = _TRAIL_STORAGE.load()
    except Exception:
        data = {}
    if isinstance(data, dict):
        _DATA = data
    else:
        _DATA = {}


def _save() -> None:
    """Persist in-memory cache."""
    try:
        _TRAIL_STORAGE.save(_DATA)
    except Exception:
        # Persistence failures should not break task logic
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_tasks(user: str) -> Dict:
    """Return tasks and completion state for ``user``."""
    _load()
    today = date.today().isoformat()
    user_data = _ensure_user_data(user, persist=True)
    daily_completed = set(user_data["daily"].get(today, []))
    once_completed = set(user_data.get("once", []))
    tasks = []
    for task in DEFAULT_TASKS:
        completed = (
            task["id"] in once_completed
            if task["type"] == "once"
            else task["id"] in daily_completed
        )
        tasks.append({**task, "completed": completed})

    if today not in user_data.get("daily_totals", {}):
        _update_daily_totals(user_data, today, completed=len(daily_completed))
        _save()

    daily_totals = dict(user_data.get("daily_totals", {}))

    return {
        "tasks": tasks,
        "xp": user_data.get("xp", 0),
        "streak": user_data.get("streak", 0),
        "daily_totals": daily_totals,
        "today": today,
    }


def mark_complete(user: str, task_id: str) -> Dict:
    """Mark ``task_id`` complete for ``user`` and return updated tasks."""
    if task_id not in TASK_IDS:
        raise KeyError(task_id)

    _load()
    today = date.today()
    today_str = today.isoformat()
    user_data = _ensure_user_data(user, persist=True)

    task = next(t for t in DEFAULT_TASKS if t["id"] == task_id)
    if task["type"] == "once":
        if task_id not in user_data["once"]:
            user_data["once"].append(task_id)
            user_data["xp"] += ONCE_XP_REWARD
    else:
        completed_today = set(user_data["daily"].get(today_str, []))
        if task_id not in completed_today:
            completed_today.add(task_id)
            user_data["daily"][today_str] = list(completed_today)
            user_data["xp"] += DAILY_XP_REWARD

        daily_completed_count = len(completed_today)
        _update_daily_totals(user_data, today_str, completed=daily_completed_count)

        if daily_completed_count == DAILY_TASK_COUNT and DAILY_TASK_COUNT:
            yesterday = (today - timedelta(days=1)).isoformat()
            if user_data.get("last_completed_day") == yesterday:
                user_data["streak"] += 1
            else:
                user_data["streak"] = 1
            user_data["last_completed_day"] = today_str

    # Ensure today's totals exist even if only "once" tasks were completed.
    _update_daily_totals(user_data, today_str)

    _save()
    return get_tasks(user)


__all__ = [
    "get_tasks",
    "mark_complete",
    "DEFAULT_TASKS",
    "DAILY_TASK_IDS",
    "ONCE_TASK_IDS",
    "DAILY_TASK_COUNT",
    "DAILY_XP_REWARD",
    "ONCE_XP_REWARD",
]
