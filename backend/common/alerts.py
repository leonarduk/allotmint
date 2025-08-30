import logging
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Dict, List, Set

from backend.config import config

logger = logging.getLogger("alerts")

# Stores alerts published during this process run
_RECENT_ALERTS: List[Dict] = []
# Signatures of recently published alerts to avoid duplicates
_RECENT_ALERT_SIGNATURES: Set[str] = set()


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

    Duplicate alerts (same ticker and message) are ignored for the duration
    of the current process run.

    Alerts may include ``instrument`` and ``state`` fields indicating the
    subject of the alert and whether a threshold was crossed.  When present,
    alerts are throttled to one per instrument per hour and are only published
    when the state changes.
    """
    
    signature = _alert_signature(alert)
    if signature in _RECENT_ALERT_SIGNATURES:
        logger.info("Duplicate alert skipped: %s", alert)
        return

    _RECENT_ALERT_SIGNATURES.add(signature)


    instrument = alert.get("instrument")
    state = alert.get("state")

    now = datetime.utcnow()

    if instrument is not None and state is not None:
        previous_state = _LAST_ALERT_STATE.get(instrument)
        last_time = _LAST_ALERT_TIME.get(instrument)

        # Only publish when state changes and at most once per hour.
        if previous_state == state:
            return
        if last_time and now - last_time < timedelta(hours=1):
            return

    alert["timestamp"] = now.isoformat()
    _RECENT_ALERTS.append(alert)
    topic_arn = config.sns_topic_arn
    if not topic_arn:
        logger.info("SNS topic ARN not configured; skipping publish")
        return

    try:
        import boto3  # type: ignore

        boto3.client("sns").publish(TopicArn=topic_arn, Message=alert["message"])
    except ModuleNotFoundError:
        logger.warning("SNS topic ARN set but boto3 not installed")
        return
    except Exception as exc:
        logger.warning("SNS publish failed: %s", exc)
        return

    if instrument is not None and state is not None:
        _LAST_ALERT_STATE[instrument] = bool(state)
        _LAST_ALERT_TIME[instrument] = now


# Backwards compatibility shim
def publish_alert(alert: Dict) -> None:
    publish_sns_alert(alert)


def get_recent_alerts(limit: int = 50) -> List[Dict]:
    """Return recent alerts, most recent last."""
    return _RECENT_ALERTS[-limit:]
