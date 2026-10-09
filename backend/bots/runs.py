"""Run-record store: one document per bot holding its most recent runs.

Every run writes a record -- including skipped and failed runs -- so the Bots
page can tell "ran and found nothing" apart from "never ran" (#8805). A record
is first saved as ``running`` and then updated in place when the run ends;
the in-progress guard in :mod:`backend.bots.runner` relies on that.

Records are kept newest first and trimmed to :data:`MAX_RUNS` per bot.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ValidationError

from backend.bots.registry import RunStatus, RunTrigger, is_valid_bot_id
from backend.bots.store import storage_for
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

MAX_RUNS = 50

# Serialises read-modify-write of a bot's run document within one process.
_lock = threading.Lock()


class RunRecord(BaseModel):
    id: str
    bot_id: str
    trigger: RunTrigger
    status: RunStatus
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    summary: Optional[str] = None
    report: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    actor: Optional[str] = None
    owner: Optional[str] = None
    model: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _storage(bot_id: str):
    if not is_valid_bot_id(bot_id):
        raise ValueError(f"Invalid bot id {bot_id!r}")
    return storage_for(f"runs/{bot_id}.json")


def _load(bot_id: str) -> List[RunRecord]:
    data = _storage(bot_id).load()
    rows = data.get("runs") if isinstance(data, dict) else None
    records: List[RunRecord] = []
    for row in rows or []:
        try:
            records.append(RunRecord.model_validate(row))
        except ValidationError as exc:
            logger.warning(
                "Ignoring malformed run record for %s: %s", sanitise_log_value(bot_id), sanitise_log_value(exc)
            )
    return records


def list_runs(bot_id: str, limit: Optional[int] = None) -> List[RunRecord]:
    """Return ``bot_id``'s runs, newest first."""

    records = _load(bot_id)
    return records[:limit] if limit is not None else records


def get_run(bot_id: str, run_id: str) -> Optional[RunRecord]:
    return next((r for r in _load(bot_id) if r.id == run_id), None)


def latest_run(bot_id: str) -> Optional[RunRecord]:
    records = _load(bot_id)
    return records[0] if records else None


def save_run(record: RunRecord) -> RunRecord:
    """Insert or replace ``record`` (matched on ``id``) and persist."""

    with _lock:
        records = [r for r in _load(record.bot_id) if r.id != record.id]
        records.append(record)
        records.sort(key=lambda r: r.started_at, reverse=True)
        payload = {"runs": [r.model_dump(mode="json") for r in records[:MAX_RUNS]]}
        _storage(record.bot_id).save(payload)
    return record


__all__ = ["MAX_RUNS", "RunRecord", "get_run", "latest_run", "list_runs", "new_run_id", "save_run"]
