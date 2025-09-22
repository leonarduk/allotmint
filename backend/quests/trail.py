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


def _ensure_user_data(user: str) -> Dict:
    """Ensure the cached state for ``user`` has all expected keys."""

    user_data = _DATA.setdefault(user, {})
    user_data.setdefault("once", [])
    user_data.setdefault("daily", {})
    user_data.setdefault("xp", 0)
    user_data.setdefault("streak", 0)
    user_data.setdefault("last_completed_day", "")
    user_data.setdefault("daily_totals", {})
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
    user_data = _ensure_user_data(user)
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

    daily_totals = dict(user_data.get("daily_totals", {}))
    daily_totals.setdefault(
        today,
        {"completed": len(daily_completed), "total": DAILY_TASK_COUNT},
    )

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
    user_data = _ensure_user_data(user)

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
        user_data["daily_totals"][today_str] = {
            "completed": daily_completed_count,
            "total": DAILY_TASK_COUNT,
        }

        if daily_completed_count == DAILY_TASK_COUNT and DAILY_TASK_COUNT:
            yesterday = (today - timedelta(days=1)).isoformat()
            if user_data.get("last_completed_day") == yesterday:
                user_data["streak"] += 1
            else:
                user_data["streak"] = 1
            user_data["last_completed_day"] = today_str

    # Ensure today's totals exist even if only "once" tasks were completed.
    daily_completed_today = len(set(user_data["daily"].get(today_str, [])))
    user_data["daily_totals"][today_str] = {
        "completed": daily_completed_today,
        "total": DAILY_TASK_COUNT,
    }

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
