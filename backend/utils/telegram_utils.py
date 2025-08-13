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


def redact_token(text: str) -> str:
    """Replace any occurrence of the Telegram token in ``text`` with ***."""
    token = app_config.telegram_bot_token
    if not token:
        return text
    return text.replace(token, "***")


class RedactTokenFilter(logging.Filter):
    """Filter that redacts the Telegram token from log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging internals
        token = app_config.telegram_bot_token
        if token:
            if isinstance(record.msg, str):
                record.msg = record.msg.replace(token, "***")
            if record.args:
                record.args = tuple(
                    arg.replace(token, "***") if isinstance(arg, str) else arg
                    for arg in record.args
                )
        return True


# Ensure all loggers redact the token
logging.getLogger().addFilter(RedactTokenFilter())

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

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": str(chat_id), "text": text},
            timeout=5,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        # Avoid leaking the token in exception messages
        raise exc.__class__(redact_token(str(exc))) from exc
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
