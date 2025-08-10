"""Utility helpers for sending messages to Telegram.

This module exposes a small helper function and a logging handler that forward
messages to a Telegram chat. The bot token and chat identifier are read from
the ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` environment variables.  If
the credentials are missing the helper functions simply skip sending so that
applications can continue operating without requiring Telegram to be
configured.
"""

from __future__ import annotations

import logging
import os
import requests


def send_message(text: str) -> None:
    """Send ``text`` to the configured Telegram chat.

    The function reads ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` from the
    environment. If either is missing the function returns without performing
    any network requests.  Any failure to contact the Telegram API will result
    in the raised ``requests.RequestException`` bubbling up to the caller so
    that it can be surfaced appropriately.
    """

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

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

