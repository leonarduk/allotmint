from __future__ import annotations

"""Simple task tracking for the Trail page.

Historically the Trail view surfaced a handful of static checklist items that
did not map to any real workflow. This rewrite replaces the static list with
tasks that reflect tangible actions derived from the user's data – e.g.
outstanding allowance headroom or missing alert configuration. Completion
state continues to be stored in a JSON document using the
``backend.common.storage`` helpers so that tests can use an in-memory file
while deployments may swap in other backends.
"""

import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List

from backend import alerts
from backend.common import allowances, compliance, data_loader
from backend.common.goals import load_goals
from backend.common.storage import get_storage
from backend.config import config

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


@dataclass(frozen=True)
class TaskDefinition:
    """Lightweight structure describing an available task."""

    id: str
    title: str
    type: str
    commentary: str


def _owner_directories() -> Iterable[str]:
    """Return the set of owners discovered in the accounts directory."""

    paths = data_loader.resolve_paths(config.repo_root, config.accounts_root)
    root = paths.accounts_root
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def _owners_for_user(user: str) -> List[str]:
    """Return the list of portfolio owners visible to ``user``."""

    user_lc = user.lower()
    owners: List[str] = []

    # First attempt to match on primary email metadata.
    paths = data_loader.resolve_paths(config.repo_root, config.accounts_root)
    root = paths.accounts_root
    for owner in _owner_directories():
        meta = data_loader.load_person_meta(owner, root)
        email = str(meta.get("email") or "").lower()
        viewers = [str(v).lower() for v in meta.get("viewers", []) if isinstance(v, str)]
        if email and email == user_lc:
            owners.append(owner)
            continue
        if user_lc and user_lc in viewers:
            owners.append(owner)

    if owners:
        return sorted(dict.fromkeys(owners))

    # Fallback to owner slug matching – either the full username or the local
    # part when ``user`` is an email address.
    candidates = [user]
    if "@" in user:
        candidates.append(user.split("@", 1)[0])
    for candidate in candidates:
        if candidate and (root / candidate).exists():
            owners.append(candidate)
    return sorted(dict.fromkeys(owners))


def _format_currency(amount: float) -> str:
    return f"£{amount:,.0f}"


def _build_allowance_tasks(owners: Iterable[str]) -> List[TaskDefinition]:
    tasks: List[TaskDefinition] = []
    tax_year = allowances.current_tax_year()
    for owner in owners:
        summary = allowances.remaining_allowances(owner, tax_year)
        for account, details in summary.items():
            remaining = float(details.get("remaining", 0.0))
            limit = float(details.get("limit", 0.0))
            if remaining <= 0:
                continue
            label_raw = account.replace("_", " ")
            account_label = label_raw.upper() if label_raw.upper() == "ISA" else label_raw.title()
            commentary = (
                f"{account_label} allowance remaining: {_format_currency(remaining)}"
                f" of {_format_currency(limit)}."
            )
            tasks.append(
                TaskDefinition(
                    id=f"{owner}_allowance_{account.lower()}",
                    title=f"Plan {account_label} contributions for {owner}",
                    type="daily",
                    commentary=commentary,
                )
            )
    return tasks


def _build_compliance_tasks(owners: Iterable[str]) -> List[TaskDefinition]:
    tasks: List[TaskDefinition] = []
    for owner in owners:
        try:
            summary = compliance.check_owner(owner, config.accounts_root)
        except FileNotFoundError:
            continue

        warnings = [w for w in summary.get("warnings", []) if isinstance(w, str)]
        if warnings:
            first = warnings[0]
            extra = len(warnings) - 1
            commentary = first if extra <= 0 else f"{first} (+{extra} more)"
            tasks.append(
                TaskDefinition(
                    id=f"{owner}_compliance_warnings",
                    title=f"Resolve compliance warnings for {owner}",
                    type="daily",
                    commentary=commentary,
                )
            )

        hold = summary.get("hold_countdowns", {})
        if isinstance(hold, dict) and hold:
            soonest = sorted(hold.items(), key=lambda item: item[1])[0]
            ticker, days = soonest
            try:
                days_int = int(days)
            except (TypeError, ValueError):
                days_int = None
            if days_int is not None:
                commentary = f"{ticker} unlocks in {days_int} day" + ("s" if days_int != 1 else "")
            else:
                commentary = f"Monitor hold periods for {ticker}"
            tasks.append(
                TaskDefinition(
                    id=f"{owner}_hold_periods",
                    title=f"Check restricted positions for {owner}",
                    type="daily",
                    commentary=commentary,
                )
            )
    return tasks


def _build_once_tasks(user: str, user_data: Dict) -> List[TaskDefinition]:
    tasks: List[TaskDefinition] = []

    # Encourage the user to model a goal if they have not already done so.
    if not load_goals(user) or "create_goal" in user_data.get("once", []):
        tasks.append(
            TaskDefinition(
                id="create_goal",
                title="Create your first savings goal",
                type="once",
                commentary="Goals help quantify long-term plans and progress.",
            )
        )

    # Configure price-drift alerts to catch meaningful moves.
    thresholds = getattr(alerts, "_USER_THRESHOLDS", {})
    if user not in thresholds or "set_alert_threshold" in user_data.get("once", []):
        # ``alerts.get_user_threshold`` falls back to the default without
        # indicating whether the user explicitly configured the value.  The
        # private ``_USER_THRESHOLDS`` cache records explicit overrides, so a
        # missing entry means the threshold still lives at the default.
        tasks.append(
            TaskDefinition(
                id="set_alert_threshold",
                title="Adjust your alert threshold",
                type="once",
                commentary="Fine-tune drift alerts so significant moves surface quickly.",
            )
        )

    # Push notifications require an explicit subscription – remind the user
    # when none is configured.
    if alerts.get_user_push_subscription(user) is None or "enable_push_notifications" in user_data.get("once", []):
        tasks.append(
            TaskDefinition(
                id="enable_push_notifications",
                title="Enable push notifications",
                type="once",
                commentary="Stay informed about nudges and alerts without opening the app.",
            )
        )

    return tasks


def _build_task_definitions(user: str, user_data: Dict) -> List[TaskDefinition]:
    """Assemble the task catalogue for ``user`` based on live data."""

    owners = _owners_for_user(user)

    daily_tasks = _build_allowance_tasks(owners) + _build_compliance_tasks(owners)
    once_tasks = _build_once_tasks(user, user_data)

    # Stable ordering keeps the UI predictable and simplifies testing.
    daily_tasks.sort(key=lambda task: task.id)
    once_tasks.sort(key=lambda task: task.id)

    return daily_tasks + once_tasks


def _update_daily_totals(
    user_data: Dict,
    day: str,
    *,
    completed: int | None = None,
    total: int | None = None,
) -> None:
    """Persist the completion totals for ``day``.

    Centralising this logic keeps the ``daily_totals`` payload consistent whether the
    data is being initialised or updated after marking tasks complete.  When
    ``completed`` is omitted the value is derived from the recorded daily tasks.
    """

    if completed is None:
        completed = len(set(user_data["daily"].get(day, [])))

    if total is None:
        existing_total = (
            user_data.get("daily_totals", {}).get(day, {}).get("total")
            if isinstance(user_data.get("daily_totals"), dict)
            else None
        )
        if existing_total is not None:
            total = existing_total
        else:
            total = len(set(user_data["daily"].get(day, [])))

    user_data.setdefault("daily_totals", {})[day] = {
        "completed": completed,
        "total": int(total),
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
    task_defs = _build_task_definitions(user, user_data)

    daily_task_ids = [task.id for task in task_defs if task.type == "daily"]
    once_task_ids = [task.id for task in task_defs if task.type == "once"]

    daily_completed = {
        task_id for task_id in user_data["daily"].get(today, []) if task_id in daily_task_ids
    }
    user_data["daily"][today] = sorted(daily_completed)
    once_completed = {
        task_id for task_id in user_data.get("once", []) if task_id in once_task_ids
    }

    tasks: List[Dict[str, object]] = []
    for task in task_defs:
        completed = (
            task.id in once_completed if task.type == "once" else task.id in daily_completed
        )
        tasks.append(
            {
                "id": task.id,
                "title": task.title,
                "type": task.type,
                "commentary": task.commentary,
                "completed": completed,
            }
        )

    _update_daily_totals(
        user_data,
        today,
        completed=len(daily_completed),
        total=len(daily_task_ids),
    )
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
    _load()
    today = date.today()
    today_str = today.isoformat()
    user_data = _ensure_user_data(user, persist=True)

    task_defs = _build_task_definitions(user, user_data)
    task_lookup = {task.id: task for task in task_defs}
    if task_id not in task_lookup:
        raise KeyError(task_id)

    daily_task_ids = [task.id for task in task_defs if task.type == "daily"]
    task = task_lookup[task_id]
    if task.type == "once":
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
        _update_daily_totals(
            user_data,
            today_str,
            completed=daily_completed_count,
            total=len(daily_task_ids),
        )

        if daily_task_ids and daily_completed_count == len(daily_task_ids):
            yesterday = (today - timedelta(days=1)).isoformat()
            if user_data.get("last_completed_day") == yesterday:
                user_data["streak"] += 1
            else:
                user_data["streak"] = 1
            user_data["last_completed_day"] = today_str

    # Ensure today's totals exist even if only "once" tasks were completed.
    _update_daily_totals(
        user_data,
        today_str,
        completed=len(set(user_data["daily"].get(today_str, []))),
        total=len(daily_task_ids),
    )

    _save()
    return get_tasks(user)


__all__ = [
    "get_tasks",
    "mark_complete",
    "DAILY_XP_REWARD",
    "ONCE_XP_REWARD",
]
