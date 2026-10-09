"""Per-owner digest settings (#10485).

Read from ``BOTS_DIGEST_SETTINGS_URI`` (``file://``, ``s3://`` or ``ssm://``,
via :func:`backend.common.storage.get_storage`), a JSON object keyed by owner.
Missing or invalid settings fall back to the defaults: a weekly digest by
email only, no Telegram, no £ amounts, and no immediate alerts (every bot's
items go only into the digest). Editing these belongs to the bot registry's
settings API (#10477); this module only reads them.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel, Field, ValidationError

from backend.bots.digest_models import DigestPeriod, Severity
from backend.common.storage import get_storage
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

SETTINGS_URI_ENV = "BOTS_DIGEST_SETTINGS_URI"


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
    data_root = getattr(config, "data_root", None)
    base = Path(data_root) if data_root else Path(__file__).resolve().parents[2] / "data"
    return f"file://{base / 'bots' / 'digest_settings.json'}"


def load_settings(owner: str) -> DigestSettings:
    """``owner``'s digest settings, or the defaults."""

    uri = os.getenv(SETTINGS_URI_ENV) or _default_uri()
    raw = get_storage(uri, param_type="String").load().get(owner)
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


__all__ = ["SETTINGS_URI_ENV", "DigestSettings", "load_settings"]
