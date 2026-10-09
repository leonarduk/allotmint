"""Thin seam between the digest and wherever bot run records are stored (#10485).

The bot registry (#10477) has not landed yet. Until it does, the digest reads
run records through :class:`RunRecordSource`, and :class:`FileRunRecordSource`
reads the layout #10477 proposes: ``<runs location>/<bot_id>/latest.json``
(``BOTS_RUNS_URI``, default ``{data_root}/bots/runs``). When the registry
lands it can implement ``RunRecordSource`` directly (its ``bots()`` replacing
:data:`KNOWN_BOTS`) and the composer does not change.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional, Protocol

from pydantic import ValidationError

from backend.bots.digest_models import BotDescriptor, BotRunRecord
from backend.bots.storage import json_storage, location
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

RUNS_URI_ENV = "BOTS_RUNS_URI"
LATEST_NAME = "latest.json"

# Bots the digest expects to hear from. A bot with no stored run shows as
# "not run yet". Replaced by the registry's list once #10477 lands.
KNOWN_BOTS: List[BotDescriptor] = [
    BotDescriptor(id="trading-agent", name="Trading agent signals", kind="rules", scope="system"),
    BotDescriptor(id="price-refresh", name="Price refresh", kind="job", scope="system"),
    BotDescriptor(id="dividend-refresh", name="Dividend refresh", kind="job", scope="system"),
    BotDescriptor(id="pension-report", name="Pension report", kind="job", scope="owner"),
    BotDescriptor(id="data-steward", name="Data steward", kind="ai", scope="system"),
    BotDescriptor(id="statement-reconciliation", name="Statement reconciliation", kind="ai", scope="owner"),
    BotDescriptor(id="plan-drift", name="Plan-drift brief", kind="ai", scope="owner"),
    BotDescriptor(id="trend-watch", name="Holding trend watch", kind="ai", scope="owner"),
    BotDescriptor(id="allowance-guardian", name="Contribution & allowance guardian", kind="rules", scope="owner"),
    BotDescriptor(id="cash-deployment", name="Cash deployment tracker", kind="rules", scope="owner"),
    BotDescriptor(id="decision-journal", name="Decision journal", kind="ai", scope="owner"),
    BotDescriptor(id="fund-data-upkeep", name="Fund data upkeep", kind="ai", scope="system"),
]


class RunRecordSource(Protocol):
    """Where the digest gets bots and their latest run records from."""

    def bots(self) -> List[BotDescriptor]:
        """Every bot the digest should report on."""

    def latest_run(self, bot_id: str) -> Optional[BotRunRecord]:
        """The bot's most recent run record, or ``None`` if it has never run."""


class FileRunRecordSource:
    """Reads ``<location>/<bot_id>/latest.json`` from a local directory or S3 prefix."""

    def __init__(self, base: Optional[str] = None, bots: Optional[List[BotDescriptor]] = None) -> None:
        self._base = base or location(RUNS_URI_ENV, "bots/runs")
        self._bots = list(bots) if bots is not None else list(KNOWN_BOTS)

    def bots(self) -> List[BotDescriptor]:
        return list(self._bots)

    def latest_run(self, bot_id: str) -> Optional[BotRunRecord]:
        raw = json_storage(self._base, bot_id, LATEST_NAME).load()
        if not raw:
            return None
        try:
            return BotRunRecord.model_validate(raw)
        except ValidationError as exc:
            # An unreadable record is a failure the owner should see, not "not run yet".
            logger.warning(
                "Unreadable run record for bot %s: %s",
                sanitise_log_value(bot_id),
                sanitise_log_value(exc.error_count()),
            )
            return BotRunRecord(
                bot_id=bot_id,
                status="failed",
                started_at=datetime.now(timezone.utc),
                error="The stored run record could not be read.",
            )


__all__ = ["KNOWN_BOTS", "FileRunRecordSource", "RunRecordSource"]
