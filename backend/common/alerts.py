import logging
from datetime import datetime
from typing import Dict, List

from backend.config import config

logger = logging.getLogger("alerts")

_RECENT_ALERTS: List[Dict] = []

def publish_alert(alert: Dict) -> None:
    """Store alert and send via SNS if configured."""
    alert["timestamp"] = datetime.utcnow().isoformat()
    _RECENT_ALERTS.append(alert)

    topic_arn = config.sns_topic_arn
    if not topic_arn:
        raise RuntimeError("missing SNS configuration")

    try:
        import boto3  # type: ignore

        boto3.client("sns").publish(TopicArn=topic_arn, Message=alert["message"])
    except ModuleNotFoundError:
        logger.warning("SNS topic ARN set but boto3 not installed")
    except Exception as exc:
        logger.warning("SNS publish failed: %s", exc)

def get_recent_alerts(limit: int = 50) -> List[Dict]:
    """Return recent alerts, most recent last."""
    return _RECENT_ALERTS[-limit:]
