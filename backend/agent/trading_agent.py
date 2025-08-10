"""Helpers for sending trading alerts via SNS or Telegram."""

from __future__ import annotations

import logging
import os

from backend.common.alerts import publish_alert
from backend.utils.telegram_utils import send_message

logger = logging.getLogger(__name__)


def send_trade_alert(message: str) -> None:
    """Send ``message`` using the configured alert transports.

    The alert is always passed to :func:`backend.common.alerts.publish_alert`
    which stores it and publishes to SNS when ``SNS_TOPIC_ARN`` is set.
    If both ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` are present in the
    environment, the message is also forwarded to Telegram via
    :func:`backend.utils.telegram_utils.send_message`.
    """

    publish_alert({"message": message})

    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        try:
            send_message(message)
        except Exception as exc:  # pragma: no cover - network errors are rare
            logger.warning("Telegram send failed: %s", exc)
