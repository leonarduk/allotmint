from __future__ import annotations

"""Simple quest tracking utilities.

This module stores a small set of daily quests and tracks completion for
individual users. Data is persisted using the same JSON storage abstraction
as :mod:`backend.alerts` to keep development lightweight while allowing
production deployments to switch storage backends via environment variables.
"""

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Dict

from backend.common.storage import get_storage
from backend.config import config

# Default quests available each day. In a real application these would likely
# be dynamic or database driven. For now we keep a tiny static list so the
# frontend has something to render.
QUEST_DEFINITIONS = [
    {"id": "check_in", "title": "Check in", "xp": 10},
    {"id": "read_article", "title": "Read a finance article", "xp": 20},
]
QUEST_IDS = {q["id"] for q in QUEST_DEFINITIONS}

# Storage setup ---------------------------------------------------------------
_DEFAULT_QUESTS_URI = (
    f"file://{(config.repo_root or Path(__file__).resolve().parents[1]) / 'data' / 'quests.json'}"
)
_QUESTS_STORAGE = get_storage(os.getenv("QUESTS_URI", _DEFAULT_QUESTS_URI))

# In-memory cache of quest progress keyed by user
_DATA: Dict[str, Dict] = {}


def _load() -> None:
    """Populate in-memory cache from persistent storage."""
    global _DATA
    if _DATA:
        return
    try:
        data = _QUESTS_STORAGE.load()
    except Exception:
        data = {}
    if isinstance(data, dict):
        _DATA = data
    else:
        _DATA = {}


def _save() -> None:
    """Persist in-memory quest state."""
    try:
        _QUESTS_STORAGE.save(_DATA)
    except Exception:
        # Persistence failures should not break quest logic
        pass


# Public API -----------------------------------------------------------------

def get_quests(user: str) -> Dict:
    """Return today's quests and progress for ``user``."""
    _load()
    today = date.today().isoformat()
    user_data = _DATA.setdefault(
        user, {"xp": 0, "streak": 0, "last_completed_day": "", "completed": {}}
    )
    completed_today = set(user_data["completed"].get(today, []))
    quests = [
        {**q, "completed": q["id"] in completed_today} for q in QUEST_DEFINITIONS
    ]
    return {"quests": quests, "xp": user_data["xp"], "streak": user_data["streak"]}


def mark_complete(user: str, quest_id: str) -> Dict:
    """Mark ``quest_id`` complete for ``user`` and update XP/streak.

    Returns the updated quest summary for the user.
    """
    if quest_id not in QUEST_IDS:
        raise KeyError(quest_id)

    _load()
    today = date.today()
    today_str = today.isoformat()
    user_data = _DATA.setdefault(
        user, {"xp": 0, "streak": 0, "last_completed_day": "", "completed": {}}
    )
    completed = set(user_data["completed"].get(today_str, []))
    if quest_id in completed:
        return get_quests(user)

    # grant XP for this quest
    xp_value = next(q["xp"] for q in QUEST_DEFINITIONS if q["id"] == quest_id)
    user_data["xp"] += xp_value
    completed.add(quest_id)
    user_data["completed"][today_str] = list(completed)

    # streak logic – increment when all quests are done for the day
    if completed == QUEST_IDS:
        yesterday = (today - timedelta(days=1)).isoformat()
        if user_data.get("last_completed_day") == yesterday:
            user_data["streak"] += 1
        else:
            user_data["streak"] = 1
        user_data["last_completed_day"] = today_str

    _save()
    return get_quests(user)


__all__ = ["get_quests", "mark_complete", "QUEST_DEFINITIONS"]
