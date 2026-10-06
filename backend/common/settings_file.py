"""Shared access to an owner's ``settings.json``.

Two writers share this file: :mod:`backend.common.user_config` (hold-day,
trade-limit and approval-exemption keys) and
:mod:`backend.common.allocation_policy` (the ``allocation_policy`` key). Each
merges its own keys into the existing content, so neither clobbers the other.

That merge is only safe if the existing content was actually read. A corrupt
file must never be treated as empty and rewritten, which would silently drop
every other key in it (#9514), so :func:`read_settings` raises
:class:`SettingsUnreadableError` instead. Readers that can carry on with
defaults catch it and log; writers let it propagate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.common.data_loader import resolve_owner_dir


class SettingsUnreadableError(RuntimeError):
    """``settings.json`` exists but cannot be parsed as a JSON object."""


def settings_path(owner: str, accounts_root: Path | None = None) -> Path:
    """Return ``owner``'s ``settings.json`` path (``FileNotFoundError`` if no such owner)."""

    return resolve_owner_dir(owner, accounts_root) / "settings.json"


def read_settings(path: Path) -> dict[str, Any]:
    """Return the settings object, ``{}`` if the file is absent or holds nothing.

    An empty (or whitespace-only) file and a JSON ``null`` carry no settings to
    lose, so they read as ``{}``. Raises :class:`SettingsUnreadableError` if
    the file exists but is anything else that is not a readable JSON object.
    """

    if not path.exists():
        return {}
    try:
        text = path.read_text()
        data = json.loads(text) if text.strip() else None
    except (OSError, ValueError) as exc:
        raise SettingsUnreadableError(f"Unreadable settings file {path.name}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SettingsUnreadableError(f"Settings file {path.name} is not a JSON object")
    return data
