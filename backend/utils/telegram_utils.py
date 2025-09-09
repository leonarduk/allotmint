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
                record.args = tuple(arg.replace(token, "***") if isinstance(arg, str) else arg for arg in record.args)
        return True


# Ensure all loggers redact the token
logging.getLogger().addFilter(RedactTokenFilter())

MESSAGE_TTL_SECONDS = 300
RATE_LIMIT_SECONDS = 1.0
MAX_RETRIES = 3

RECENT_MESSAGES: dict[str, float] = {}
_NEXT_ALLOWED_TIME = 0.0


def send_message(text: str) -> None:
    if app_config.offline_mode:
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

    missing = []
    if not token:
        missing.append("token")
    if not chat_id:
        missing.append("chat_id")
    if missing:
        logger.debug(
            "Missing Telegram configuration: %s",
            ", ".join(missing),
            extra={"skip_telegram": True},
        )
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
                logger.warning("Telegram rate limit hit; backing off", extra={"skip_telegram": True})
                warning_logged = True
            retry_after = resp.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after is not None else backoff
            except ValueError:
                delay = backoff
            delay = max(0, min(delay, 60))
            _NEXT_ALLOWED_TIME = time.time() + delay
            time.sleep(delay)
            backoff = min(delay * 2, 60)
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
            if not app_config.offline_mode:
                send_message(message)
        except Exception:
            # Let logging's handleError respect logging.raiseExceptions.
            self.handleError(record)
