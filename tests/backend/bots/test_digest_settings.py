"""Per-owner digest settings storage (#10502). Synthetic owners only."""

from __future__ import annotations

import pytest

from backend.bots import digest_settings
from backend.bots.digest_settings import DigestSettings


class _S3Like:
    """A storage whose strict read fails, as S3 does on a transient error or a 403."""

    def __init__(self):
        self.saved = None

    def load(self):
        return {}

    def load_existing(self):
        raise RuntimeError("AccessDenied")

    def save(self, data):
        self.saved = data


def test_save_keeps_other_owners(monkeypatch, tmp_path):
    monkeypatch.setenv(digest_settings.SETTINGS_URI_ENV, f"file://{tmp_path / 'settings.json'}")
    digest_settings.save_settings("bob", DigestSettings(period="monthly"))

    digest_settings.save_settings("alex", DigestSettings(send_when_empty=True))

    assert digest_settings.load_settings("bob").period == "monthly"
    assert digest_settings.load_settings("alex").send_when_empty is True


def test_failed_read_never_overwrites_every_owners_settings(monkeypatch):
    storage = _S3Like()
    monkeypatch.setattr(digest_settings, "_storage", lambda: storage)

    with pytest.raises(RuntimeError):
        digest_settings.save_settings("alex", DigestSettings())

    assert storage.saved is None
