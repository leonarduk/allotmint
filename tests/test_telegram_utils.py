import logging
from types import SimpleNamespace
from unittest.mock import patch

import requests

import backend.utils.telegram_utils as telegram_utils


def test_send_message_requires_config(monkeypatch):
    telegram_utils.RECENT_MESSAGES.clear()
    monkeypatch.setattr(telegram_utils.config, "telegram_bot_token", None, raising=False)
    monkeypatch.setattr(telegram_utils.config, "telegram_chat_id", None, raising=False)
    # should silently return when config missing
    telegram_utils.send_message("hi")


def test_log_handler_without_config(monkeypatch):
    """Logging via ``TelegramLogHandler`` should not raise without credentials."""
    telegram_utils.RECENT_MESSAGES.clear()
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
    telegram_utils.RECENT_MESSAGES.clear()
    telegram_utils._NEXT_ALLOWED_TIME = 0
    monkeypatch.setattr(telegram_utils, "OFFLINE_MODE", False)
    monkeypatch.setattr(telegram_utils.config, "telegram_bot_token", "T")
    monkeypatch.setattr(telegram_utils.config, "telegram_chat_id", "C")
    monkeypatch.setattr(telegram_utils.time, "sleep", lambda s: None)

    def fake_post(url, data, timeout):
        assert url == "https://api.telegram.org/botT/sendMessage"
        assert data == {"chat_id": "C", "text": "ok"}
        assert timeout == 5
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    with patch("backend.utils.telegram_utils.requests.post", fake_post):
        telegram_utils.send_message("ok")


def test_deduplicates_messages_within_ttl(monkeypatch):
    telegram_utils.RECENT_MESSAGES.clear()
    telegram_utils._NEXT_ALLOWED_TIME = 0
    monkeypatch.setattr(telegram_utils, "OFFLINE_MODE", False)
    monkeypatch.setattr(telegram_utils.config, "telegram_bot_token", "T")
    monkeypatch.setattr(telegram_utils.config, "telegram_chat_id", "C")
    monkeypatch.setattr(telegram_utils.time, "time", lambda: 1000.0)
    monkeypatch.setattr(telegram_utils.time, "sleep", lambda s: None)

    calls = []

    def fake_post(url, data, timeout):
        calls.append(1)
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    with patch("backend.utils.telegram_utils.requests.post", fake_post):
        telegram_utils.send_message("dup")
        telegram_utils.send_message("dup")

    assert len(calls) == 1


def test_sends_messages_after_ttl(monkeypatch):
    telegram_utils.RECENT_MESSAGES.clear()
    telegram_utils._NEXT_ALLOWED_TIME = 0
    monkeypatch.setattr(telegram_utils, "OFFLINE_MODE", False)
    monkeypatch.setattr(telegram_utils.config, "telegram_bot_token", "T")
    monkeypatch.setattr(telegram_utils.config, "telegram_chat_id", "C")

    times = iter([1000.0] * 3 + [1000.0 + telegram_utils.MESSAGE_TTL_SECONDS + 1] * 3)
    monkeypatch.setattr(telegram_utils.time, "time", lambda: next(times))
    monkeypatch.setattr(telegram_utils.time, "sleep", lambda s: None)

    calls = []

    def fake_post(url, data, timeout):
        calls.append(1)
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    with patch("backend.utils.telegram_utils.requests.post", fake_post):
        telegram_utils.send_message("hi")
        telegram_utils.send_message("hi")

    assert len(calls) == 2


def test_handles_http_429(monkeypatch, caplog):
    telegram_utils.RECENT_MESSAGES.clear()
    telegram_utils._NEXT_ALLOWED_TIME = 0
    monkeypatch.setattr(telegram_utils, "OFFLINE_MODE", False)
    monkeypatch.setattr(telegram_utils.config, "telegram_bot_token", "T")
    monkeypatch.setattr(telegram_utils.config, "telegram_chat_id", "C")

    responses = iter(
        [
            SimpleNamespace(status_code=429, raise_for_status=lambda: None),
            SimpleNamespace(status_code=200, raise_for_status=lambda: None),
        ]
    )

    calls = []

    def fake_post(url, data, timeout):
        calls.append(1)
        return next(responses)

    monkeypatch.setattr(telegram_utils.time, "sleep", lambda s: None)

    with patch("backend.utils.telegram_utils.requests.post", fake_post), caplog.at_level(logging.WARNING):
        telegram_utils.send_message("rate")

    assert len(calls) == 2
    assert any("rate limit" in r.message.lower() for r in caplog.records)


def test_handles_timeout(monkeypatch, caplog):
    telegram_utils.RECENT_MESSAGES.clear()
    telegram_utils._NEXT_ALLOWED_TIME = 0
    monkeypatch.setattr(telegram_utils, "OFFLINE_MODE", False)
    monkeypatch.setattr(telegram_utils.config, "telegram_bot_token", "T")
    monkeypatch.setattr(telegram_utils.config, "telegram_chat_id", "C")

    def fake_post(url, data, timeout):
        raise telegram_utils.req_exc.Timeout()

    with patch("backend.utils.telegram_utils.requests.post", fake_post), caplog.at_level(logging.WARNING):
        telegram_utils.send_message("timeout")

    assert any("timeout" in r.message.lower() for r in caplog.records)


def test_redacts_token_from_errors(monkeypatch, caplog):
    telegram_utils.RECENT_MESSAGES.clear()
    monkeypatch.setattr(telegram_utils, "OFFLINE_MODE", False)
    token = "SECRET"
    monkeypatch.setattr(telegram_utils.config, "telegram_bot_token", token)
    monkeypatch.setattr(telegram_utils.config, "telegram_chat_id", "C")
    telegram_utils.logger.addFilter(telegram_utils.RedactTokenFilter())

    def fake_post(url, data, timeout):
        raise requests.RequestException(f"boom {url}")

    with patch("backend.utils.telegram_utils.requests.post", fake_post):
        with caplog.at_level(logging.WARNING):
            telegram_utils.send_message("hi")

    assert token not in caplog.text
    assert "***" in caplog.text
