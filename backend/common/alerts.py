import logging
from datetime import datetime
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


def publish_sns_alert(alert: Dict) -> None:
    """Store alert and send via SNS if configured.

    Duplicate alerts (same ticker and message) are ignored for the duration
    of the current process run.
    """
    signature = _alert_signature(alert)
    if signature in _RECENT_ALERT_SIGNATURES:
        logger.info("Duplicate alert skipped: %s", alert)
        return

    _RECENT_ALERT_SIGNATURES.add(signature)
    alert["timestamp"] = datetime.utcnow().isoformat()
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
    except Exception as exc:
        logger.warning("SNS publish failed: %s", exc)


# Backwards compatibility shim
def publish_alert(alert: Dict) -> None:
    publish_sns_alert(alert)


def get_recent_alerts(limit: int = 50) -> List[Dict]:
    """Return recent alerts, most recent last."""
    return _RECENT_ALERTS[-limit:]
