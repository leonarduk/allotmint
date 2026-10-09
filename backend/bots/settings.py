"""Per-bot settings, stored in the data store and validated on every read.

A bot's effective settings are its ``default_settings()`` (current config
values) overlaid with whatever has been saved for it. Stored values that no
longer validate (e.g. after a schema change) are logged and ignored rather
than breaking the bot.

Only public, non-secret values belong here: settings are returned verbatim by
the API. Secrets stay in server config.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from pydantic import ValidationError

from backend.bots.registry import Bot, BotSettings, is_valid_bot_id
from backend.bots.store import storage_for
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "settings.json"
_lock = threading.Lock()


def load_stored_settings(bot_id: str) -> Dict[str, Any]:
    """Return the raw values saved for ``bot_id`` (``{}`` when none)."""

    if not is_valid_bot_id(bot_id):
        raise ValueError(f"Invalid bot id {bot_id!r}")
    data = storage_for(_SETTINGS_KEY).load()
    bots = data.get("bots") if isinstance(data, dict) else None
    stored = bots.get(bot_id) if isinstance(bots, dict) else None
    return dict(stored) if isinstance(stored, dict) else {}


def load_settings(bot: Bot) -> BotSettings:
    """Return ``bot``'s effective, validated settings."""

    defaults = bot.default_settings()
    stored = load_stored_settings(bot.id)
    if stored:
        try:
            return bot.settings_model.model_validate({**defaults, **stored})
        except ValidationError as exc:
            logger.warning(
                "Stored settings for bot %s are invalid; using defaults: %s",
                sanitise_log_value(bot.id),
                sanitise_log_value(exc),
            )
    return bot.settings_model.model_validate(defaults)


def save_settings(bot: Bot, values: Dict[str, Any], *, actor: Optional[str] = None) -> BotSettings:
    """Validate ``values`` against ``bot.settings_model``, persist and audit.

    Raises :class:`pydantic.ValidationError` on invalid input; nothing is
    written in that case.
    """

    validated = bot.settings_model.model_validate(values)
    before = load_settings(bot).model_dump(mode="json")
    after = validated.model_dump(mode="json")
    with _lock:
        storage = storage_for(_SETTINGS_KEY)
        data = storage.load()
        if not isinstance(data, dict):
            data = {}
        bots = data.get("bots") if isinstance(data.get("bots"), dict) else {}
        bots[bot.id] = after
        data["bots"] = bots
        storage.save(data)
    _audit(bot.id, before, after, actor)
    return validated


def _audit(bot_id: str, before: Dict[str, Any], after: Dict[str, Any], actor: Optional[str]) -> None:
    """Record the change in the admin audit trail (same log as timeseries edits)."""

    from backend.data_quality.audit import append_audit

    changed = sorted(k for k in after if before.get(k) != after.get(k))
    logger.info(
        "Bot %s settings updated by %s: %s",
        sanitise_log_value(bot_id),
        sanitise_log_value(actor),
        sanitise_log_value(changed),
    )
    try:
        append_audit(
            action="bot_settings_update",
            issue_id=f"bot:{bot_id}",
            entity={"bot_id": bot_id},
            before=before,
            after=after,
            actor=actor,
            extra={"kind": "bot_settings", "changed": changed},
        )
    except OSError as exc:
        # The change is saved; losing the audit line is reported, not hidden.
        logger.error(
            "Failed to audit settings change for bot %s: %s", sanitise_log_value(bot_id), sanitise_log_value(exc)
        )


__all__ = ["load_settings", "load_stored_settings", "save_settings"]
