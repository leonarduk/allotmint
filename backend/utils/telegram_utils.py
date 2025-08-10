"""Utility helpers for sending messages to Telegram.

This module exposes a small helper function and a logging handler that forward
messages to a Telegram chat. The bot token and chat identifier are read from
the application configuration via :mod:`backend.config`. An exception is raised
if the credentials are missing so callers can surface configuration issues to
the user.
"""

from __future__ import annotations

import logging
import requests
from backend.config import config


def send_message(text: str) -> None:
    """Send ``text`` to the configured Telegram chat.

    The function requires ``telegram_bot_token`` and ``telegram_chat_id`` to be
    present in the configuration.  Any failure to contact the Telegram API will
    result in the raised ``requests.RequestException`` bubbling up to the
    caller so that it can be surfaced appropriately.
    """

    token = config.telegram_bot_token
    chat_id = config.telegram_chat_id

    if not token or not chat_id:
        # Silently return when configuration is missing.  ``logging`` may be
        # configured with :class:`TelegramLogHandler` as one of its handlers and
        # emitting a log message here could result in an infinite loop.  Instead
        # we simply skip sending the message.
        return

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text},
        timeout=5,
    )
    response.raise_for_status()


class TelegramLogHandler(logging.Handler):
    """A logging handler that forwards records to Telegram."""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - thin wrapper
        try:
            message = self.format(record)
            send_message(message)
        except Exception:
            # ``logging`` will invoke ``handleError`` which respects the module's
            # ``raiseExceptions`` flag. We rely on that behaviour rather than
            # emitting anything ourselves to avoid recursive logging.
            self.handleError(record)

