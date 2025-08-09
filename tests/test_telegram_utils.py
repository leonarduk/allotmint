from types import SimpleNamespace
from unittest.mock import patch
import pytest

from backend.utils.telegram_utils import send_message


def test_send_message_requires_config(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(RuntimeError):
        send_message("hi")


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
