"""Nudge scheduling and subscription management.

This module implements a lightweight reminder system similar to the alert
infrastructure.  User preferences (reminder frequency and snooze state) are
persisted using the same storage abstraction as :mod:`backend.alerts` and a
simple ``lambda_handler`` is provided so the module can be triggered from a
CloudWatch cron event or similar scheduler.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from backend.common.alerts import publish_alert
from backend.common.storage import get_storage
from backend.config import config

logger = logging.getLogger("nudges")

_DEFAULT_FREQ_DAYS = 7
# Allowed reminder frequency range (in days)
_MIN_FREQ_DAYS = 1
_MAX_FREQ_DAYS = 30

# S3 object key for persisted subscriptions
_SUBSCRIPTIONS_KEY = "nudges/subscriptions.json"

_DEFAULT_SUBSCRIPTIONS_URI = (
    f"file://{(config.repo_root or Path(__file__).resolve().parents[1]) / 'data' / 'nudge_subscriptions.json'}"
)

try:
    _SUBSCRIPTION_STORAGE = get_storage(
        os.getenv("NUDGE_SUBSCRIPTIONS_URI", _DEFAULT_SUBSCRIPTIONS_URI)
    )
except Exception as exc:  # pragma: no cover - configuration errors
    logger.error("Failed to initialise nudge storage: %s", exc)
    _SUBSCRIPTION_STORAGE = get_storage(_DEFAULT_SUBSCRIPTIONS_URI)

# in-memory cache of subscription prefs
_SUBSCRIPTIONS: Dict[str, Dict] = {}

# recently generated nudges for retrieval by the API
_RECENT_NUDGES: List[Dict] = []


def _load_state() -> None:
    """Populate caches from configured storage."""
    if _SUBSCRIPTIONS or _RECENT_NUDGES:
        return
    try:
        data = _SUBSCRIPTION_STORAGE.load()
    except Exception as exc:  # pragma: no cover - storage backend failures
        logger.warning("Failed to load nudge storage: %s", exc)
        return
    if not isinstance(data, dict):
        return
    # backwards compatibility: old format only stored subscriptions
    subs = data.get("subscriptions", data)
    nudges = data.get("recent_nudges", [])
    if isinstance(subs, dict):
        _SUBSCRIPTIONS.update(subs)
    if isinstance(nudges, list):
        _RECENT_NUDGES.extend(nudges)


def _save_state() -> None:
    """Persist current subscriptions and nudges to storage."""
    try:
        _SUBSCRIPTION_STORAGE.save(
            {
                "subscriptions": _SUBSCRIPTIONS,
                "recent_nudges": _RECENT_NUDGES[-50:],
            }
        )
    except Exception as exc:  # pragma: no cover - storage backend failures
        logger.error("Failed to save nudge storage: %s", exc)


def set_user_nudge(user: str, frequency: int, snooze_until: Optional[str] = None) -> None:
    """Create or update nudge settings for ``user``."""
    _load_state()
    freq = int(frequency) if frequency is not None else _DEFAULT_FREQ_DAYS
    freq = min(max(freq, _MIN_FREQ_DAYS), _MAX_FREQ_DAYS)
    _SUBSCRIPTIONS[user] = {
        "frequency": freq,
        "snoozed_until": snooze_until,
        "last_sent": _SUBSCRIPTIONS.get(user, {}).get("last_sent"),
    }
    _save_state()


def snooze_user(user: str, days: int) -> None:
    """Snooze nudges for ``user`` by ``days`` days."""
    _load_state()
    if user not in _SUBSCRIPTIONS:
        _SUBSCRIPTIONS[user] = {"frequency": _DEFAULT_FREQ_DAYS}
    until = datetime.now(UTC) + timedelta(days=days)
    _SUBSCRIPTIONS[user]["snoozed_until"] = until.isoformat()
    _save_state()


def iter_due_users(now: Optional[datetime] = None) -> Iterable[str]:
    """Yield users whose reminders are due at ``now``."""
    _load_state()
    now = now or datetime.now(UTC)
    for user, cfg in _SUBSCRIPTIONS.items():
        freq = cfg.get("frequency", _DEFAULT_FREQ_DAYS)
        last = cfg.get("last_sent")
        snoozed = cfg.get("snoozed_until")
        if snoozed:
            try:
                if now < datetime.fromisoformat(snoozed):
                    continue
            except Exception:  # pragma: no cover - malformed timestamp
                pass
        if not last:
            yield user
            continue
        try:
            if now - datetime.fromisoformat(last) >= timedelta(days=freq):
                yield user
        except Exception:  # pragma: no cover - malformed timestamp
            yield user


def send_due_nudges() -> None:
    """Generate reminder alerts for all due users."""
    now = datetime.now(UTC)
    for user in list(iter_due_users(now)):
        message = f"Reminder for {user}"
        publish_alert({"ticker": "NUDGE", "user": user, "message": message})
        _RECENT_NUDGES.append({"id": user, "message": message, "timestamp": now.isoformat()})
        _SUBSCRIPTIONS[user]["last_sent"] = now.isoformat()
    if _RECENT_NUDGES:
        _save_state()


def get_recent_nudges(limit: int = 50) -> List[Dict]:
    """Return recently generated nudges."""
    _load_state()
    return _RECENT_NUDGES[-limit:]


@dataclass
class Event:
    """Minimal event wrapper for scheduled execution."""

    source: str | None = None


def lambda_handler(event: Optional[Event] = None, _context: Optional[dict] = None):
    """Entry point for AWS Lambda / cron scheduling."""
    send_due_nudges()
    return {"status": "ok"}


__all__ = [
    "set_user_nudge",
    "snooze_user",
    "iter_due_users",
    "send_due_nudges",
    "get_recent_nudges",
    "lambda_handler",
]
