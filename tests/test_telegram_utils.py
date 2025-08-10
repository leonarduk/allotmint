from types import SimpleNamespace
from unittest.mock import patch
import pytest

import backend.utils.telegram_utils as telegram_utils


def test_send_message_requires_config(monkeypatch):
    monkeypatch.setattr(telegram_utils.config, "telegram_bot_token", None, raising=False)
    monkeypatch.setattr(telegram_utils.config, "telegram_chat_id", None, raising=False)
    with pytest.raises(RuntimeError):
        telegram_utils.send_message("hi")


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
