"""Alert evaluation and user threshold management.

This module evaluates metric drift against user configurable thresholds.  If
an observed value deviates from a baseline by more than the configured
percentage an alert is published through :mod:`backend.common.alerts`.

User thresholds are persisted in a tiny JSON file under ``data`` which acts
as a lightweight database suitable for tests and development environments.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from backend.common.alerts import publish_alert
from backend.config import config

DEFAULT_THRESHOLD_PCT = 0.05  # default 5% threshold

# Path used to store user specific thresholds
_SETTINGS_PATH = (config.repo_root or Path(__file__).resolve().parents[1]) / "data" / "alert_thresholds.json"

# Path used to store push subscription details
_SUBSCRIPTIONS_PATH = (
    (config.repo_root or Path(__file__).resolve().parents[1])
    / "data"
    / "push_subscriptions.json"
)

# In-memory cache of settings
_USER_THRESHOLDS: Dict[str, float] = {}

# In-memory cache of push subscriptions
_PUSH_SUBSCRIPTIONS: Dict[str, Dict] = {}


def _load_settings() -> None:
    """Load threshold settings from ``_SETTINGS_PATH`` into memory."""
    global _USER_THRESHOLDS
    if _USER_THRESHOLDS:
        return
    try:
        if _SETTINGS_PATH.exists():
            _USER_THRESHOLDS = {k: float(v) for k, v in json.loads(_SETTINGS_PATH.read_text()).items()}
    except Exception:
        _USER_THRESHOLDS = {}


def _load_subscriptions() -> None:
    """Load push subscription data into memory."""
    global _PUSH_SUBSCRIPTIONS
    if _PUSH_SUBSCRIPTIONS:
        return
    try:
        if _SUBSCRIPTIONS_PATH.exists():
            _PUSH_SUBSCRIPTIONS = json.loads(_SUBSCRIPTIONS_PATH.read_text())
    except Exception:
        _PUSH_SUBSCRIPTIONS = {}


def _save_settings() -> None:
    """Persist in-memory settings to ``_SETTINGS_PATH``."""
    try:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_PATH.write_text(json.dumps(_USER_THRESHOLDS))
    except Exception:
        # Persistence failure should not block alerting
        pass


def _save_subscriptions() -> None:
    """Persist push subscriptions to disk."""
    try:
        _SUBSCRIPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SUBSCRIPTIONS_PATH.write_text(json.dumps(_PUSH_SUBSCRIPTIONS))
    except Exception:
        pass


_load_settings()
_load_subscriptions()


def get_user_threshold(user: str, default: float = DEFAULT_THRESHOLD_PCT) -> float:
    """Return threshold percentage for ``user`` or ``default`` if unset."""
    return _USER_THRESHOLDS.get(user, default)


def set_user_threshold(user: str, threshold: float) -> None:
    """Set the threshold percentage for ``user`` and persist it."""
    _USER_THRESHOLDS[user] = float(threshold)
    _save_settings()


def set_user_push_subscription(user: str, subscription: Dict) -> None:
    """Store ``subscription`` information for ``user``."""
    _PUSH_SUBSCRIPTIONS[user] = subscription
    _save_subscriptions()


def remove_user_push_subscription(user: str) -> None:
    """Remove push subscription for ``user`` if present."""
    if user in _PUSH_SUBSCRIPTIONS:
        del _PUSH_SUBSCRIPTIONS[user]
        _save_subscriptions()


def get_user_push_subscription(user: str) -> Optional[Dict]:
    """Return push subscription for ``user`` if configured."""
    return _PUSH_SUBSCRIPTIONS.get(user)


def iter_push_subscriptions() -> Iterable[Dict]:
    """Iterate over stored push subscription dicts."""
    return list(_PUSH_SUBSCRIPTIONS.values())


def send_push_notification(message: str) -> None:
    """Send ``message`` to all registered push subscriptions.

    Uses ``pywebpush`` when available.  If no subscriptions or the required
    VAPID credentials are missing, the function exits silently.
    """

    subscriptions = list(iter_push_subscriptions())
    if not subscriptions:
        return

    vapid_key = os.getenv("VAPID_PRIVATE_KEY")
    vapid_email = os.getenv("VAPID_EMAIL")
    if not (vapid_key and vapid_email):
        logging.getLogger("alerts").info(
            "VAPID credentials not configured; skipping push notification"
        )
        return

    try:
        from pywebpush import webpush  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        logging.getLogger("alerts").info(
            "pywebpush not installed; skipping push notification"
        )
        return

    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub,
                data=message,
                vapid_private_key=vapid_key,
                vapid_claims={"sub": f"mailto:{vapid_email}"},
            )
        except Exception as exc:  # pragma: no cover - network errors
            logging.getLogger("alerts").warning("Web push failed: %s", exc)


@dataclass
class EvaluationResult:
    """Result information returned by :func:`evaluate_drift`."""

    triggered: bool
    drift_pct: float


def evaluate_drift(
    user: str,
    baseline: float,
    value: float,
    *,
    threshold: Optional[float] = None,
    metric: str = "value",
) -> EvaluationResult:
    """Check for drift beyond ``threshold`` and publish an alert when exceeded.

    Parameters
    ----------
    user:
        Identifier for the user whose threshold should be applied.
    baseline:
        Reference value to compare against.
    value:
        Observed value.
    threshold:
        Optional override for the threshold percentage.
    metric:
        Name of the metric; used only for alert message formatting.
    """

    if baseline == 0:
        return EvaluationResult(False, 0.0)

    threshold = threshold if threshold is not None else get_user_threshold(user)
    drift_pct = (value - baseline) / baseline

    if abs(drift_pct) >= threshold:
        publish_alert(
            {
                "user": user,
                "metric": metric,
                "baseline": baseline,
                "value": value,
                "drift_pct": round(drift_pct, 4),
                "message": f"{metric} drift {drift_pct*100:.2f}% exceeds {threshold*100:.2f}% for {user}",
            }
        )
        return EvaluationResult(True, drift_pct)

    return EvaluationResult(False, drift_pct)
