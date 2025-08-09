import os
import logging
from datetime import datetime
from typing import Dict, List

import boto3

logger = logging.getLogger("alerts")

_RECENT_ALERTS: List[Dict] = []

def publish_alert(alert: Dict) -> None:
    """Store alert and send via SNS if configured."""
    alert["timestamp"] = datetime.utcnow().isoformat()
    _RECENT_ALERTS.append(alert)

    topic_arn = os.getenv("SNS_TOPIC_ARN")
    if topic_arn:
        try:
            boto3.client("sns").publish(TopicArn=topic_arn, Message=alert["message"])
        except Exception as exc:
            logger.warning("SNS publish failed: %s", exc)
    else:
        logger.info("ALERT: %s", alert["message"])

def get_recent_alerts(limit: int = 50) -> List[Dict]:
    """Return recent alerts, most recent last."""
    return _RECENT_ALERTS[-limit:]
