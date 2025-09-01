"""Alert evaluation and user threshold management.

This module evaluates metric drift against user configurable thresholds. If
an observed value deviates from a baseline by more than the configured
percentage an alert is published through :mod:`backend.common.alerts`.

User thresholds and web push subscriptions are persisted via a tiny JSON
object stored in a configurable backend (local file, S3 object or AWS
Parameter Store).  Local file storage keeps tests and development
environments lightweight while production deployments can point to managed
AWS services.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from backend.common.alerts import publish_alert

DEFAULT_THRESHOLD_PCT = 0.05  # default 5% threshold

# S3 object keys used to store alert data
_THRESHOLDS_KEY = "alerts/alert_thresholds.json"
_SUBSCRIPTIONS_KEY = "alerts/push_subscriptions.json"

from backend.common.storage import get_storage
from backend.config import config

logger = logging.getLogger("alerts")

# Storage locations for thresholds and push subscriptions.  URIs may point to
# ``file://`` paths, ``s3://`` objects or ``ssm://`` parameters.
_DEFAULT_SETTINGS_URI = (
    f"file://{(config.repo_root or Path(__file__).resolve().parents[1]) / 'data' / 'alert_thresholds.json'}"
)
_DEFAULT_SUBSCRIPTIONS_URI = (
    f"file://{(config.repo_root or Path(__file__).resolve().parents[1]) / 'data' / 'push_subscriptions.json'}"
)

try:
    _SETTINGS_STORAGE = get_storage(os.getenv("ALERT_THRESHOLDS_URI", _DEFAULT_SETTINGS_URI))
except Exception as exc:  # pragma: no cover - configuration errors
    logger.error("Failed to initialize settings storage: %s", exc)
    _SETTINGS_STORAGE = get_storage(_DEFAULT_SETTINGS_URI)

try:
    _SUBSCRIPTIONS_STORAGE = get_storage(os.getenv("PUSH_SUBSCRIPTIONS_URI", _DEFAULT_SUBSCRIPTIONS_URI))
except Exception as exc:  # pragma: no cover - configuration errors
    logger.error("Failed to initialize subscriptions storage: %s", exc)
    _SUBSCRIPTIONS_STORAGE = get_storage(_DEFAULT_SUBSCRIPTIONS_URI)

# In-memory cache of settings
_USER_THRESHOLDS: Dict[str, float] = {}

# In-memory cache of push subscriptions
_PUSH_SUBSCRIPTIONS: Dict[str, Dict] = {}


def _s3_client():
    """Return an S3 client or ``None`` when unavailable."""
    try:  # pragma: no cover - optional dependency
        import boto3  # type: ignore
    except Exception:
        logging.getLogger("alerts").error("boto3 not installed; S3 unavailable")
        return None
    try:
        return boto3.client("s3")
    except Exception:  # pragma: no cover - client creation failure
        logging.getLogger("alerts").exception("Failed to create S3 client")
        return None


def _data_bucket() -> Optional[str]:
    """Return the configured data bucket or ``None`` if unset."""
    return os.getenv("DATA_BUCKET")


def _load_settings() -> None:
    """Load threshold settings into memory from configured storage."""
    global _USER_THRESHOLDS
    if _USER_THRESHOLDS:
        return
    bucket = _data_bucket()
    if bucket:
        s3 = _s3_client()
        if s3:
            try:
                obj = s3.get_object(Bucket=bucket, Key=_THRESHOLDS_KEY)
                _USER_THRESHOLDS = {k: float(v) for k, v in json.loads(obj["Body"].read().decode()).items()}
                return
            except Exception:
                logging.getLogger("alerts").exception("Failed to load alert thresholds from S3")
    try:
        data = _SETTINGS_STORAGE.load()
        _USER_THRESHOLDS = {k: float(v) for k, v in data.items()}
    except Exception as exc:  # pragma: no cover - storage backend failures
        logger.warning("Failed to load user thresholds: %s", exc)
        _USER_THRESHOLDS = {}


def _load_subscriptions() -> None:
    """Load push subscription data into memory from configured storage."""
    global _PUSH_SUBSCRIPTIONS
    if _PUSH_SUBSCRIPTIONS:
        return
    bucket = _data_bucket()
    if bucket:
        s3 = _s3_client()
        if s3:
            try:
                obj = s3.get_object(Bucket=bucket, Key=_SUBSCRIPTIONS_KEY)
                _PUSH_SUBSCRIPTIONS = json.loads(obj["Body"].read().decode())
                return
            except Exception:
                logging.getLogger("alerts").exception("Failed to load push subscriptions from S3")
    try:
        _PUSH_SUBSCRIPTIONS = _SUBSCRIPTIONS_STORAGE.load()
    except Exception as exc:  # pragma: no cover - storage backend failures
        logger.warning("Failed to load push subscriptions: %s", exc)
        _PUSH_SUBSCRIPTIONS = {}


def _save_settings() -> None:
    """Persist in-memory settings to configured storage."""
    bucket = _data_bucket()
    if bucket:
        s3 = _s3_client()
        if s3:
            try:
                try:
                    obj = s3.get_object(Bucket=bucket, Key=_THRESHOLDS_KEY)
                    current = json.loads(obj["Body"].read().decode())
                except Exception:
                    current = {}
                current.update(_USER_THRESHOLDS)
                s3.put_object(
                    Bucket=bucket,
                    Key=_THRESHOLDS_KEY,
                    Body=json.dumps(current),
                )
                _USER_THRESHOLDS.update({k: float(v) for k, v in current.items()})
                return
            except Exception:
                logging.getLogger("alerts").exception("Failed to persist alert thresholds to S3")
    try:
        _SETTINGS_STORAGE.save(_USER_THRESHOLDS)
    except Exception as exc:  # pragma: no cover - storage backend failures
        # Persistence failure should not block alerting
        logger.warning("Failed to save user thresholds: %s", exc)


def _save_subscriptions() -> None:
    """Persist push subscriptions to configured storage."""
    bucket = _data_bucket()
    if bucket:
        s3 = _s3_client()
        if s3:
            try:
                try:
                    obj = s3.get_object(Bucket=bucket, Key=_SUBSCRIPTIONS_KEY)
                    current = json.loads(obj["Body"].read().decode())
                except Exception:
                    current = {}
                current.update(_PUSH_SUBSCRIPTIONS)
                s3.put_object(
                    Bucket=bucket,
                    Key=_SUBSCRIPTIONS_KEY,
                    Body=json.dumps(current),
                )
                _PUSH_SUBSCRIPTIONS.update(current)
                return
            except Exception:
                logging.getLogger("alerts").exception("Failed to persist push subscriptions to S3")
    try:
        _SUBSCRIPTIONS_STORAGE.save(_PUSH_SUBSCRIPTIONS)
    except Exception as exc:  # pragma: no cover - storage backend failures
        logger.warning("Failed to save push subscriptions: %s", exc)


_load_settings()
_load_subscriptions()


def get_user_threshold(user: str, default: float = DEFAULT_THRESHOLD_PCT) -> float:
    """Return threshold percentage for ``user`` or ``default`` if unset."""
    _load_settings()
    return _USER_THRESHOLDS.get(user, default)


def set_user_threshold(user: str, threshold: float) -> None:
    """Set the threshold percentage for ``user`` and persist it."""
    _load_settings()
    _USER_THRESHOLDS[user] = float(threshold)
    _save_settings()


def set_user_push_subscription(user: str, subscription: Dict) -> None:
    """Store ``subscription`` information for ``user``."""
    _load_subscriptions()
    _PUSH_SUBSCRIPTIONS[user] = subscription
    _save_subscriptions()


def remove_user_push_subscription(user: str) -> None:
    """Remove push subscription for ``user`` if present."""
    _load_subscriptions()
    if user in _PUSH_SUBSCRIPTIONS:
        del _PUSH_SUBSCRIPTIONS[user]
        _save_subscriptions()


def get_user_push_subscription(user: str) -> Optional[Dict]:
    """Return push subscription for ``user`` if configured."""
    _load_subscriptions()
    return _PUSH_SUBSCRIPTIONS.get(user)


def iter_push_subscriptions() -> Iterable[Dict]:
    """Iterate over stored push subscription dicts."""
    _load_subscriptions()
    return list(_PUSH_SUBSCRIPTIONS.values())


def send_push_notification(message: str) -> None:
    """Send ``message`` to all registered push subscriptions.

    Uses ``pywebpush`` when available.  When push is not available the message
    is published via SNS/email using :func:`publish_alert`.
    """

    subscriptions = list(iter_push_subscriptions())
    if not subscriptions:
        publish_alert({"message": message})
        return

    vapid_key = os.getenv("VAPID_PRIVATE_KEY")
    vapid_email = os.getenv("VAPID_EMAIL")
    if not (vapid_key and vapid_email):
        logger.info("VAPID credentials not configured; falling back to SNS")
        publish_alert({"message": message})
        return

    try:
        from pywebpush import webpush  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        logger.info("pywebpush not installed; falling back to SNS")
        publish_alert({"message": message})
        return

    sent = False
    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub,
                data=message,
                vapid_private_key=vapid_key,
                vapid_claims={"sub": f"mailto:{vapid_email}"},
            )
            sent = True
        except Exception as exc:  # pragma: no cover - network errors
            logger.warning("Web push failed: %s", exc)

    if not sent:
        publish_alert({"message": message})


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
