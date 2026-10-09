"""Where the digest gets bots and their latest runs from (#10485).

The digest reads through :class:`RunRecordSource`, so tests can supply
synthetic records. :class:`RegistryRunRecordSource` is the real one: it lists
the bot registry's bots (#10477, :func:`backend.bots.registry.list_bots`) and
reads their run records (:mod:`backend.bots.runs`).

A bot contributes digest items by returning them in its run report:
``RunResult(report={"digest_items": [DigestItem dicts], ...})``. A malformed
item is skipped with a warning; the rest of the run still counts.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Protocol

from pydantic import ValidationError

from backend.bots import registry, runs
from backend.bots.digest_models import BotDescriptor, BotRunRecord, DigestItem
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

DIGEST_ITEMS_KEY = "digest_items"


class RunRecordSource(Protocol):
    """Where the digest gets bots and their latest run records from."""

    def bots(self) -> List[BotDescriptor]:
        """Every bot the digest should report on."""

    def latest_run(self, bot_id: str) -> Optional[BotRunRecord]:
        """The bot's most recent finished run, or ``None`` if it has never run."""


def digest_items_from_report(bot_id: str, report: Any) -> List[DigestItem]:
    """The valid ``digest_items`` in a run report; malformed ones are skipped."""

    raw = report.get(DIGEST_ITEMS_KEY) if isinstance(report, dict) else None
    items: List[DigestItem] = []
    for row in raw if isinstance(raw, list) else []:
        try:
            items.append(DigestItem.model_validate(row))
        except ValidationError as exc:
            logger.warning(
                "Skipping malformed digest item from bot %s (%s errors)",
                sanitise_log_value(bot_id),
                sanitise_log_value(exc.error_count()),
            )
    return items


class RegistryRunRecordSource:
    """Bots from the registry; latest finished run from the registry's run store."""

    def bots(self) -> List[BotDescriptor]:
        return [BotDescriptor(id=b.id, name=b.name, kind=b.kind, scope=b.scope) for b in registry.list_bots()]

    def latest_run(self, bot_id: str) -> Optional[BotRunRecord]:
        # A run still in progress has nothing to report yet: use the last finished one.
        record = next((r for r in runs.list_runs(bot_id) if r.status != "running"), None)
        if record is None or record.status == "running":
            return None
        return BotRunRecord(
            bot_id=bot_id,
            status=record.status,
            started_at=record.started_at,
            finished_at=record.finished_at,
            summary=record.summary or "",
            error=record.error,
            digest_items=digest_items_from_report(bot_id, record.report),
        )


__all__ = ["DIGEST_ITEMS_KEY", "RegistryRunRecordSource", "RunRecordSource", "digest_items_from_report"]
