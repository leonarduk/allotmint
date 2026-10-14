"""Recent alerts: publish (store + optional SNS) and list them (#10802).

Published alerts and the de-dup signatures are kept in one JSON document so
they survive a backend restart or a Lambda cold start:

``{"alerts": [...oldest first...], "signatures": [...oldest first...],
"throttle": {instrument: {"state": bool, "time": iso}}}``

``throttle`` carries the per-instrument state/hour throttle, so a restart
does not let an instrument alert again inside its hour.

The location is ``ALERTS_HISTORY_URI`` when set, else
``s3://$DATA_BUCKET/alerts/recent_alerts.json`` on AWS, else
``data/alerts/recent_alerts.json`` in the repo, through the same JSON storage
abstraction as the other small stores (``backend.common.storage``).

S3 has no append, so the document is rewritten on each publish and capped to
the newest ``MAX_STORED_ALERTS`` alerts and ``MAX_STORED_SIGNATURES``
signatures; that cap is the retention. Alerts stay global (not per owner), as
they were before persistence.

A lock serialises the read-modify-write within one process. Separate processes
(e.g. concurrent Lambda invocations) are last-writer-wins: an alert written
between another writer's read and write can be lost. That is accepted for a
notification feed; SNS delivery is unaffected.
"""

import logging
import os
import threading
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Dict, List, Optional, Set

from backend.common.storage import JSONStorage, get_storage
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

ALERTS_HISTORY_ENV = "ALERTS_HISTORY_URI"
_S3_KEY = "alerts/recent_alerts.json"
# Retention: the newest alerts / signatures kept in the persisted document.
MAX_STORED_ALERTS = 500
MAX_STORED_SIGNATURES = 2000

# In-memory mirror of the persisted alerts, oldest first
_RECENT_ALERTS: List[Dict] = []
# Signatures of recently published alerts to avoid duplicates
_RECENT_ALERT_SIGNATURES: Set[str] = set()
# The same signatures in publish order, so the oldest can be dropped at the cap
_SIGNATURE_ORDER: List[str] = []

_lock = threading.RLock()


def _history_uri() -> str:
    explicit = os.getenv(ALERTS_HISTORY_ENV)
    if explicit:
        return explicit
    bucket = os.getenv("DATA_BUCKET")
    if bucket:
        return f"s3://{bucket}/{_S3_KEY}"
    root = config.repo_root or Path(__file__).resolve().parents[2]
    return f"file://{Path(root) / 'data' / 'alerts' / 'recent_alerts.json'}"


def _storage() -> JSONStorage:
    return get_storage(_history_uri())


def _load_history() -> None:
    """Replace the in-memory alerts and signatures with the persisted ones.

    The storage backends return ``{}`` when a read fails, which is
    indistinguishable from "nothing stored yet". An empty read therefore keeps
    whatever is already in memory rather than wiping it, so a transient S3
    failure cannot erase alerts that the next save would then overwrite.
    """

    data = _storage().load()
    if not isinstance(data, dict):
        return
    stored_alerts = [a for a in data.get("alerts") or [] if isinstance(a, dict)]
    stored_signatures = [str(s) for s in data.get("signatures") or [] if isinstance(s, str)]
    if not stored_alerts and not stored_signatures:
        _restore_throttle(data.get("throttle"))
        return
    _RECENT_ALERTS[:] = stored_alerts
    _SIGNATURE_ORDER[:] = list(dict.fromkeys(stored_signatures))
    _RECENT_ALERT_SIGNATURES.clear()
    _RECENT_ALERT_SIGNATURES.update(_SIGNATURE_ORDER)
    # The stored throttle is authoritative too, like the alerts and signatures.
    _LAST_ALERT_STATE.clear()
    _LAST_ALERT_TIME.clear()
    _restore_throttle(data.get("throttle"))


def _restore_throttle(stored: object) -> None:
    """Merge persisted per-instrument throttle entries into memory."""

    if not isinstance(stored, dict):
        return
    for instrument, entry in stored.items():
        if not isinstance(entry, dict):
            continue
        try:
            when = datetime.fromisoformat(str(entry["time"]))
        except (KeyError, ValueError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        _LAST_ALERT_STATE[str(instrument)] = bool(entry.get("state"))
        _LAST_ALERT_TIME[str(instrument)] = when


def _throttle_document() -> Dict[str, Dict]:
    return {
        instrument: {"state": state, "time": _LAST_ALERT_TIME[instrument].isoformat()}
        for instrument, state in _LAST_ALERT_STATE.items()
        if instrument in _LAST_ALERT_TIME
    }


def _save_history() -> None:
    """Persist the newest alerts and signatures; log, never raise, on failure."""

    del _RECENT_ALERTS[:-MAX_STORED_ALERTS]
    dropped = _SIGNATURE_ORDER[:-MAX_STORED_SIGNATURES]
    del _SIGNATURE_ORDER[:-MAX_STORED_SIGNATURES]
    _RECENT_ALERT_SIGNATURES.difference_update(dropped)
    try:
        _storage().save({"alerts": _RECENT_ALERTS, "signatures": _SIGNATURE_ORDER, "throttle": _throttle_document()})
    except Exception as exc:
        logger.warning("Failed to persist alerts: %s", sanitise_log_value(exc))


def _remember_signature(signature: str) -> None:
    _RECENT_ALERT_SIGNATURES.add(signature)
    _SIGNATURE_ORDER.append(signature)


def _alert_signature(alert: Dict) -> str:
    """Return a hash signature for ``alert`` based on ticker and message."""
    ticker = alert.get("ticker", "")
    message = alert.get("message", "")
    return sha256(f"{ticker}|{message}".encode()).hexdigest()


# Track last published state and time per instrument to throttle alerts and only
# emit notifications when the state changes (e.g. threshold crossed vs. not).
_LAST_ALERT_STATE: Dict[str, bool] = {}
_LAST_ALERT_TIME: Dict[str, datetime] = {}


def publish_sns_alert(alert: Dict) -> None:
    """Store alert and send via SNS if configured.

    Duplicate alerts (same ticker and message) are ignored while their
    signature is in the persisted history, including across restarts.

    Alerts may include ``instrument`` and ``state`` fields indicating the
    subject of the alert and whether a threshold was crossed.  When present,
    alerts are throttled to one per instrument per hour and are only published
    when the state changes.
    """

    with _lock:
        _publish_locked(alert)


def _publish_locked(alert: Dict) -> None:
    _load_history()
    signature = _alert_signature(alert)
    if signature in _RECENT_ALERT_SIGNATURES:
        logger.info("Duplicate alert skipped: %s", sanitise_log_value(alert))
        return

    _remember_signature(signature)

    instrument = alert.get("instrument")
    state = alert.get("state")

    now = datetime.now(UTC)

    if instrument is not None and state is not None:
        previous_state = _LAST_ALERT_STATE.get(instrument)
        last_time = _LAST_ALERT_TIME.get(instrument)

        # Only publish when state changes and at most once per hour.
        if previous_state == state or (last_time and now - last_time < timedelta(hours=1)):
            # Throttled: not listed, but its signature still counts as seen.
            _save_history()
            return

    alert["timestamp"] = now.isoformat()
    _RECENT_ALERTS.append(alert)
    # Throttle once the alert has reached the user: sent via SNS, or listed
    # in-app only because SNS is not configured. A failed SNS send does not
    # throttle, so the next alert retries delivery.
    if _send_sns(alert) is not False and instrument is not None and state is not None:
        _LAST_ALERT_STATE[instrument] = bool(state)
        _LAST_ALERT_TIME[instrument] = now
    _save_history()


def _send_sns(alert: Dict) -> Optional[bool]:
    """Publish ``alert`` to SNS; return whether it was sent, ``None`` when SNS is not configured."""

    topic_arn = config.sns_topic_arn
    if not topic_arn:
        logger.info("SNS topic ARN not configured; skipping publish")
        return None

    try:
        import boto3  # type: ignore

        boto3.client("sns").publish(TopicArn=topic_arn, Message=alert["message"])
    except ModuleNotFoundError:
        logger.warning("SNS topic ARN set but boto3 not installed")
        return False
    except Exception as exc:
        logger.warning("SNS publish failed: %s", sanitise_log_value(exc))
        return False
    return True


# Backwards compatibility shim
def publish_alert(alert: Dict) -> None:
    publish_sns_alert(alert)


def get_recent_alerts(limit: int = 50) -> List[Dict]:
    """Return recent alerts, most recent last, read from the persisted history.

    At most ``MAX_STORED_ALERTS`` are retained, whatever ``limit`` asks for.
    """
    with _lock:
        _load_history()
        return list(_RECENT_ALERTS[-limit:])


def clear_state() -> None:
    """Clear all in-memory alert tracking state.

    Resets recent alerts, their signatures and per-instrument throttling
    metadata so tests or callers can start from a clean slate. The persisted
    history is left alone, so this also simulates a process restart.
    """

    _RECENT_ALERTS.clear()
    _RECENT_ALERT_SIGNATURES.clear()
    _SIGNATURE_ORDER.clear()
    _LAST_ALERT_STATE.clear()
    _LAST_ALERT_TIME.clear()


__all__ = [
    "publish_sns_alert",
    "publish_alert",
    "get_recent_alerts",
    "clear_state",
]
