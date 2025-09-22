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
#   "last_completed_day": "YYYY-MM-DD",
#   "daily_totals": { "YYYY-MM-DD": int }
# }
_DATA: Dict[str, Dict] = {}

XP_PER_COMPLETION = 10
DAILY_TASK_IDS = {t["id"] for t in DEFAULT_TASKS if t["type"] == "daily"}


def _user_defaults() -> Dict:
    """Return the default payload for new users."""

    return {
        "once": [],
        "daily": {},
        "xp": 0,
        "streak": 0,
        "last_completed_day": "",
        "daily_totals": {},
    }


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
    user_data = _DATA.setdefault(user, _user_defaults())
    # ensure new keys exist for previously stored data
    for key, default in _user_defaults().items():
        user_data.setdefault(key, default if not isinstance(default, dict) else {})

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
    return {
        "tasks": tasks,
        "xp": user_data.get("xp", 0),
        "streak": user_data.get("streak", 0),
        "daily_totals": dict(user_data.get("daily_totals", {})),
    }


def mark_complete(user: str, task_id: str) -> Dict:
    """Mark ``task_id`` complete for ``user`` and return updated tasks."""
    if task_id not in TASK_IDS:
        raise KeyError(task_id)

    _load()
    today = date.today().isoformat()
    user_data = _DATA.setdefault(user, _user_defaults())
    for key, default in _user_defaults().items():
        user_data.setdefault(key, default if not isinstance(default, dict) else {})

    task = next(t for t in DEFAULT_TASKS if t["id"] == task_id)
    if task["type"] == "once":
        if task_id not in user_data["once"]:
            user_data["once"].append(task_id)
            user_data["xp"] = user_data.get("xp", 0) + XP_PER_COMPLETION
    else:
        completed_today = set(user_data["daily"].get(today, []))
        if task_id not in completed_today:
            completed_today.add(task_id)
            user_data["daily"][today] = list(completed_today)
            user_data["xp"] = user_data.get("xp", 0) + XP_PER_COMPLETION
            user_data.setdefault("daily_totals", {})[today] = len(completed_today)

            if completed_today.issuperset(DAILY_TASK_IDS):
                yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
                if user_data.get("last_completed_day") == yesterday:
                    user_data["streak"] = user_data.get("streak", 0) + 1
                else:
                    user_data["streak"] = 1
                user_data["last_completed_day"] = today
        else:
            # ensure totals exist even when task already marked complete earlier today
            user_data.setdefault("daily_totals", {}).setdefault(today, len(completed_today))

    _save()
    return get_tasks(user)


__all__ = ["get_tasks", "mark_complete", "DEFAULT_TASKS"]
