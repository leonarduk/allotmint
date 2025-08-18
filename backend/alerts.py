"""Alert evaluation and user threshold management.

This module evaluates metric drift against user configurable thresholds.  If
an observed value deviates from a baseline by more than the configured
percentage an alert is published through :mod:`backend.common.alerts`.

User thresholds are persisted in a tiny JSON file under ``data`` which acts
as a lightweight database suitable for tests and development environments.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from backend.config import config
from backend.common.alerts import publish_alert

DEFAULT_THRESHOLD_PCT = 0.05  # default 5% threshold

# Path used to store user specific thresholds
_SETTINGS_PATH = (
    (config.repo_root or Path(__file__).resolve().parents[1])
    / "data"
    / "alert_thresholds.json"
)

# In-memory cache of settings
_USER_THRESHOLDS: Dict[str, float] = {}


def _load_settings() -> None:
    """Load threshold settings from ``_SETTINGS_PATH`` into memory."""
    global _USER_THRESHOLDS
    if _USER_THRESHOLDS:
        return
    try:
        if _SETTINGS_PATH.exists():
            _USER_THRESHOLDS = {
                k: float(v) for k, v in json.loads(_SETTINGS_PATH.read_text()).items()
            }
    except Exception:
        _USER_THRESHOLDS = {}


def _save_settings() -> None:
    """Persist in-memory settings to ``_SETTINGS_PATH``."""
    try:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_PATH.write_text(json.dumps(_USER_THRESHOLDS))
    except Exception:
        # Persistence failure should not block alerting
        pass


_load_settings()


def get_user_threshold(user: str, default: float = DEFAULT_THRESHOLD_PCT) -> float:
    """Return threshold percentage for ``user`` or ``default`` if unset."""
    return _USER_THRESHOLDS.get(user, default)


def set_user_threshold(user: str, threshold: float) -> None:
    """Set the threshold percentage for ``user`` and persist it."""
    _USER_THRESHOLDS[user] = float(threshold)
    _save_settings()


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
