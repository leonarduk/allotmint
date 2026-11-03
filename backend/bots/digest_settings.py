"""Per-owner digest settings (#10485).

Read from ``BOTS_DIGEST_SETTINGS_URI`` (``file://``, ``s3://`` or ``ssm://``,
via :func:`backend.common.storage.get_storage`), default
``<BOTS_STORAGE_URI>/digest_settings.json``: a JSON object keyed by owner.
Missing or invalid settings fall back to the defaults: a weekly digest by
email only, no Telegram, no £ amounts, and no immediate alerts (every bot's
items go only into the digest).

The settings belong to each owner, not to a bot, so they are edited through
the owner-scoped ``PUT /bots/digest/{owner}/settings``
(:mod:`backend.routes.bots_digest`, #10502) with :func:`save_settings`, not
the admin-only registry settings API.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from backend.bots.digest_models import DigestPeriod, Severity
from backend.bots.store import storage_base
from backend.common.storage import get_storage
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

SETTINGS_URI_ENV = "BOTS_DIGEST_SETTINGS_URI"
# Serialises the read-modify-write of the shared settings document in-process.
_lock = threading.Lock()


class DigestSettings(BaseModel):
    period: DigestPeriod = "weekly"
    email_enabled: bool = True
    telegram_enabled: bool = False
    # £/$/€ amounts are hidden in email and Telegram unless the owner opts in.
    include_balances: bool = False
    # Send a one-line "nothing needs you" digest when there are no items.
    send_when_empty: bool = False
    per_bot_cap: int = Field(default=5, ge=1, le=50)
    # bot id -> severities that also alert immediately (default: digest only).
    alert_immediately_for: Dict[str, List[Severity]] = Field(default_factory=dict)


def _default_uri() -> str:
    return f"{storage_base()}/digest_settings.json"


def _storage() -> Any:
    return get_storage(os.getenv(SETTINGS_URI_ENV) or _default_uri(), param_type="String")


def load_settings(owner: str) -> DigestSettings:
    """``owner``'s digest settings, or the defaults."""

    raw = _storage().load().get(owner)
    if not isinstance(raw, dict):
        return DigestSettings()
    try:
        return DigestSettings.model_validate(raw)
    except ValidationError as exc:
        logger.warning(
            "Invalid digest settings for %s (%s errors); using defaults",
            sanitise_log_value(owner),
            sanitise_log_value(exc.error_count()),
        )
        return DigestSettings()


def _load_for_update(storage: Any) -> Dict[str, Any]:
    """The whole settings document for a read-modify-write.

    On S3 a failed read raises (``load_existing``) instead of reading as empty,
    which would overwrite every other owner's settings; a document not yet
    written is ``{}``.
    """

    load_existing = getattr(storage, "load_existing", None)
    data: Optional[Dict[str, Any]] = load_existing() if callable(load_existing) else storage.load()
    return data if isinstance(data, dict) else {}


def save_settings(owner: str, settings: DigestSettings) -> DigestSettings:
    """Store ``owner``'s settings, leaving every other owner's untouched."""

    with _lock:
        storage = _storage()
        data = _load_for_update(storage)
        data[owner] = settings.model_dump(mode="json")
        storage.save(data)
    return settings


__all__ = ["SETTINGS_URI_ENV", "DigestSettings", "load_settings", "save_settings"]
