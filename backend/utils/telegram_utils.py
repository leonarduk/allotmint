# backend/utils/telegram.py
"""
Utility helpers for sending messages to Telegram.

Reads bot token and chat id from the application configuration
(via backend.common.config). If either is missing, it silently
returns to avoid recursive logging loops.
"""

from __future__ import annotations

import logging
import time
import requests

from backend.config import config as app_config

# expose config for tests/backwards compat
config = app_config
OFFLINE_MODE = config.offline_mode
logger = logging.getLogger(__name__)

MESSAGE_TTL_SECONDS = 300
RECENT_MESSAGES: dict[str, float] = {}


def send_message(text: str) -> None:
    if OFFLINE_MODE:
        logger.info(f"Offline-alert: {text}")
        return

    now = time.time()
    expired = [m for m, ts in RECENT_MESSAGES.items() if now - ts > MESSAGE_TTL_SECONDS]
    for m in expired:
        del RECENT_MESSAGES[m]

    if text in RECENT_MESSAGES:
        return

    """Send `text` to the configured Telegram chat."""
    token = app_config.telegram_bot_token
    chat_id = app_config.telegram_chat_id

    # Avoid emitting logs here (could recurse if TelegramLogHandler is active)
    if not token or not chat_id:
        return

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": str(chat_id), "text": text},
        timeout=5,
    )
    resp.raise_for_status()
    RECENT_MESSAGES[text] = now


class TelegramLogHandler(logging.Handler):
    """A logging handler that forwards records to Telegram."""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - thin wrapper
        try:
            message = self.format(record)
            if not OFFLINE_MODE:
                send_message(message)
        except Exception:
            # Let logging's handleError respect logging.raiseExceptions.
            self.handleError(record)
