from types import SimpleNamespace
from unittest.mock import patch
import logging

import backend.utils.telegram_utils as telegram_utils


def test_send_message_requires_config(monkeypatch):
    monkeypatch.setattr(telegram_utils.config, "telegram_bot_token", None, raising=False)
    monkeypatch.setattr(telegram_utils.config, "telegram_chat_id", None, raising=False)
    # should silently return when config missing
    telegram_utils.send_message("hi")

def test_log_handler_without_config(monkeypatch):
    """Logging via ``TelegramLogHandler`` should not raise without credentials."""

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    handler = telegram_utils.TelegramLogHandler()
    logger = logging.getLogger("telegram-util-test")
    logger.addHandler(handler)
    try:
        with patch(
            "backend.utils.telegram_utils.requests.post",
            side_effect=AssertionError("requests.post should not be called"),
        ):
            logger.error("oops")
    finally:
        logger.removeHandler(handler)


def test_send_message_success(monkeypatch):
    monkeypatch.setattr(telegram_utils.config, "telegram_bot_token", "T")
    monkeypatch.setattr(telegram_utils.config, "telegram_chat_id", "C")

    def fake_post(url, data, timeout):
        assert url == "https://api.telegram.org/botT/sendMessage"
        assert data == {"chat_id": "C", "text": "ok"}
        assert timeout == 5
        return SimpleNamespace(raise_for_status=lambda: None)

    with patch("backend.utils.telegram_utils.requests.post", fake_post):
        telegram_utils.send_message("ok")
