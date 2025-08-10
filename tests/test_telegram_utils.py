from types import SimpleNamespace
from unittest.mock import patch
import logging

from backend.utils.telegram_utils import send_message, TelegramLogHandler


def test_send_message_skips_without_config(monkeypatch):
    """The helper should be a no-op when credentials are missing."""

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    def fake_post(*args, **kwargs):  # pragma: no cover - shouldn't be called
        raise AssertionError("requests.post should not be called")

    with patch("backend.utils.telegram_utils.requests.post", fake_post):
        send_message("hi")


def test_log_handler_without_config(monkeypatch):
    """Logging via ``TelegramLogHandler`` should not raise without credentials."""

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    handler = TelegramLogHandler()
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
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "C")

    def fake_post(url, data, timeout):
        assert url == "https://api.telegram.org/botT/sendMessage"
        assert data == {"chat_id": "C", "text": "ok"}
        assert timeout == 5
        return SimpleNamespace(raise_for_status=lambda: None)

    with patch("backend.utils.telegram_utils.requests.post", fake_post):
        send_message("ok")
