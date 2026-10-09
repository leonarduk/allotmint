"""Deliver the digest and immediate alerts over the existing transports (#10485).

* Telegram/SNS go through the trading agent's
  :func:`backend.agent.trading_agent.send_trade_alert`, so they keep the same
  configuration and "Telegram only off AWS" rule as trade alerts.
* Email goes through :mod:`backend.emails.bots_digest` (SES/Jinja2).

Money amounts are hidden in every message unless the owner opted in with
``include_balances``. Item text is never logged.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Iterable, List, Optional, Set

from backend.bots.digest_models import Digest, DigestItem
from backend.bots.digest_settings import DigestSettings
from backend.bots.digest_store import DIGESTS_URI_ENV
from backend.bots.storage import json_storage, location
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

ALERTED_NAME = "alerted.json"
HIDDEN_AMOUNT = "[amount hidden]"

Sender = Callable[[str], None]

_AMOUNT = re.compile(
    r"(?:[£$€]\s?-?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|m|bn)\b)?)" r"|(?:\b-?\d[\d,]*(?:\.\d+)?\s?(?:GBP|GBX|USD|EUR)\b)",
    re.IGNORECASE,
)


def redact_amounts(text: str, include_balances: bool = False) -> str:
    """Replace £/$/€ and GBP/USD/EUR amounts unless ``include_balances``."""

    return text if include_balances else _AMOUNT.sub(HIDDEN_AMOUNT, text)


def _default_sender(message: str) -> None:
    # Imported lazily: the trading agent pulls in pandas and price tooling.
    from backend.agent.trading_agent import send_trade_alert

    send_trade_alert(message)


def format_item(item: DigestItem, include_balances: bool) -> str:
    line = f"[{item.severity.value}] {item.title}"
    if item.summary:
        line += f": {item.summary}"
    return redact_amounts(line, include_balances)


def digest_text(digest: Digest, settings: DigestSettings) -> str:
    """Plain-text digest for Telegram/SNS."""

    lines = [f"AllotMint bots digest for {digest.owner}", redact_amounts(digest.opener, settings.include_balances)]
    for item in digest.items:
        marker = "NEW " if item.status == "new" else ""
        lines.append(f"- {marker}{format_item(item, settings.include_balances)}")
    if digest.resolved:
        lines.append(f"Resolved: {len(digest.resolved)}")
    return "\n".join(lines)


def _alerted_keys(owner: str) -> Set[str]:
    keys = json_storage(location(DIGESTS_URI_ENV, "digests"), owner, ALERTED_NAME).load().get("keys")
    return {str(k) for k in keys} if isinstance(keys, list) else set()


def _save_alerted_keys(owner: str, keys: Iterable[str]) -> None:
    storage = json_storage(location(DIGESTS_URI_ENV, "digests"), owner, ALERTED_NAME)
    storage.save({"keys": sorted(keys)})


def send_immediate_alerts(
    owner: str,
    items: List[DigestItem],
    settings: DigestSettings,
    send: Optional[Sender] = None,
) -> List[str]:
    """Alert now for items whose bot is set to ``alert_immediately_for`` their severity.

    Each ``dedupe_key`` alerts once while it stays open; the items still appear
    in the digest so there is one record. Returns the keys alerted this call.
    """

    sender = send or _default_sender
    already = _alerted_keys(owner)
    sent: List[str] = []
    for item in items:
        wanted = settings.alert_immediately_for.get(item.bot, [])
        if item.severity not in wanted or item.dedupe_key in already or item.dedupe_key in sent:
            continue
        try:
            sender(format_item(item, settings.include_balances))
        except Exception as exc:
            logger.error(
                "Immediate alert failed for bot %s: %s",
                sanitise_log_value(item.bot),
                sanitise_log_value(type(exc).__name__),
            )
            continue
        sent.append(item.dedupe_key)
    open_keys = {item.dedupe_key for item in items}
    # Forget keys that closed, so a finding that reopens alerts again.
    _save_alerted_keys(owner, (already | set(sent)) & open_keys)
    return sent


def send_digest_telegram(digest: Digest, settings: DigestSettings, send: Optional[Sender] = None) -> None:
    (send or _default_sender)(digest_text(digest, settings))


__all__ = [
    "HIDDEN_AMOUNT",
    "digest_text",
    "format_item",
    "redact_amounts",
    "send_digest_telegram",
    "send_immediate_alerts",
]
