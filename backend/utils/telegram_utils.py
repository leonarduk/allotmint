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
from typing import Any

import requests
from requests import exceptions as req_exc

from backend.config import config as app_config

# expose config for tests/backwards compat
config = app_config
OFFLINE_MODE = config.offline_mode
logger = logging.getLogger(__name__)

MESSAGE_TTL_SECONDS = 300
RATE_LIMIT_SECONDS = 1.0
MAX_RETRIES = 3

RECENT_MESSAGES: dict[str, float] = {}
_NEXT_ALLOWED_TIME = 0.0


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

    token = app_config.telegram_bot_token
    chat_id = app_config.telegram_chat_id

    if not token or not chat_id:
        return

    global _NEXT_ALLOWED_TIME
    if now < _NEXT_ALLOWED_TIME:
        time.sleep(_NEXT_ALLOWED_TIME - now)

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data: dict[str, Any] = {"chat_id": str(chat_id), "text": text}

    backoff = 1.0
    warning_logged = False

    for _ in range(MAX_RETRIES):
        try:
            resp = requests.post(url, data=data, timeout=5)
        except req_exc.Timeout:
            logger.warning("Timeout sending Telegram message", extra={"skip_telegram": True})
            return
        except req_exc.RequestException as exc:
            logger.warning(f"Error sending Telegram message: {exc}", extra={"skip_telegram": True})
            return

        if resp.status_code == 429:
            if not warning_logged:
                logger.warning(
                    "Telegram rate limit hit; backing off", extra={"skip_telegram": True}
                )
                warning_logged = True
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue

        try:
            resp.raise_for_status()
        except req_exc.RequestException as exc:
            logger.warning(f"Error sending Telegram message: {exc}", extra={"skip_telegram": True})
            return

        RECENT_MESSAGES[text] = time.time()
        _NEXT_ALLOWED_TIME = time.time() + RATE_LIMIT_SECONDS
        return


class TelegramLogHandler(logging.Handler):
    """A logging handler that forwards records to Telegram."""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - thin wrapper
        if getattr(record, "skip_telegram", False):
            return
        try:
            message = self.format(record)
            if not OFFLINE_MODE:
                send_message(message)
        except Exception:
            # Let logging's handleError respect logging.raiseExceptions.
            self.handleError(record)
