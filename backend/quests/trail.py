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
DAILY_TASK_IDS = {t["id"] for t in DEFAULT_TASKS if t["type"] == "daily"}

DAILY_XP = 10
ONCE_XP = 25
DAILY_COMPLETION_BONUS = 15

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
#   "last_completed_day": "YYYY-MM-DD" | "",
#   "daily_totals": { "YYYY-MM-DD": int }
# }
_DATA: Dict[str, Dict] = {}


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
    """Return tasks and completion state for ``user`` along with summary data."""
    _load()
    today = date.today().isoformat()
    user_data = _DATA.setdefault(
        user,
        {
            "once": [],
            "daily": {},
            "xp": 0,
            "streak": 0,
            "last_completed_day": "",
            "daily_totals": {},
        },
    )
    # Backwards compatibility for persisted data created before gamification
    user_data.setdefault("once", [])
    user_data.setdefault("daily", {})
    user_data.setdefault("xp", 0)
    user_data.setdefault("streak", 0)
    user_data.setdefault("last_completed_day", "")
    daily_totals = user_data.setdefault("daily_totals", {})
    # Ensure totals are populated for historic days
    for day, completed in user_data["daily"].items():
        daily_totals.setdefault(day, len(completed))
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
        "xp": user_data["xp"],
        "streak": user_data["streak"],
        "daily_totals": daily_totals,
        "today_completed": len(daily_completed),
        "today_total": len(DAILY_TASK_IDS),
    }


def mark_complete(user: str, task_id: str) -> Dict:
    """Mark ``task_id`` complete for ``user`` and return updated summary."""
    if task_id not in TASK_IDS:
        raise KeyError(task_id)

    _load()
    today = date.today()
    today_str = today.isoformat()
    user_data = _DATA.setdefault(
        user,
        {
            "once": [],
            "daily": {},
            "xp": 0,
            "streak": 0,
            "last_completed_day": "",
            "daily_totals": {},
        },
    )

    user_data.setdefault("xp", 0)
    user_data.setdefault("streak", 0)
    user_data.setdefault("last_completed_day", "")
    user_data.setdefault("daily", {})
    user_data.setdefault("once", [])
    daily_totals = user_data.setdefault("daily_totals", {})

    task = next(t for t in DEFAULT_TASKS if t["id"] == task_id)
    xp_awarded = 0
    if task["type"] == "once":
        if task_id not in user_data["once"]:
            user_data["once"].append(task_id)
            xp_awarded += ONCE_XP
    else:
        completed_today = set(user_data["daily"].get(today_str, []))
        if task_id not in completed_today:
            completed_today.add(task_id)
            user_data["daily"][today_str] = list(completed_today)
            daily_totals[today_str] = len(completed_today)
            xp_awarded += DAILY_XP

            if completed_today == DAILY_TASK_IDS:
                yesterday = (today - timedelta(days=1)).isoformat()
                if user_data.get("last_completed_day") == yesterday:
                    user_data["streak"] += 1
                else:
                    user_data["streak"] = 1
                user_data["last_completed_day"] = today_str
                xp_awarded += DAILY_COMPLETION_BONUS

    if xp_awarded:
        user_data["xp"] += xp_awarded

    _save()
    return get_tasks(user)


__all__ = [
    "get_tasks",
    "mark_complete",
    "DEFAULT_TASKS",
    "DAILY_XP",
    "ONCE_XP",
    "DAILY_COMPLETION_BONUS",
]
