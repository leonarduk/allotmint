"""Utility helpers for sending messages to Telegram.

This module exposes a small helper function and a logging handler that forward
messages to a Telegram chat. The bot token and chat identifier are read from
the ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` environment variables. If
either variable is missing the helpers become no-ops so they can be safely used
in tests or environments where Telegram notifications are not desired.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests


def send_message(text: str) -> None:
    """Send ``text`` to the configured Telegram chat.

    The message is only sent when both ``TELEGRAM_BOT_TOKEN`` and
    ``TELEGRAM_CHAT_ID`` environment variables are present.  Failure to send
    the message is deliberately ignored so that logging remains best-effort.
    """

    token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id: Optional[str] = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return

    try:
        requests.get(
            f"https://api.telegram.org/bot{token}/sendMessage",
            params={"chat_id": chat_id, "text": text},
            timeout=5,
        )
    except Exception:
        # Errors here should not disrupt the application flow; logging failures
        # are ignored.
        pass


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

