"""Lightweight analytics event storage helpers.

The production service forwards analytics events to a dedicated pipeline, but
for the local demo environment we persist events to newline-delimited JSON
files under ``data/analytics``.  This module centralises the filesystem access
so both API routes and tests can append and read events without duplicating
path resolution, locking or serialisation concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterator, List, Optional

from backend.common.data_loader import resolve_paths
from backend.config import config

_LOCK = Lock()


@dataclass(frozen=True)
class AnalyticsEvent:
    """Representation of a stored analytics event."""

    source: str
    event: str
    user: Optional[str]
    occurred_at: datetime
    metadata: Optional[Dict[str, Any]]

    def as_serialisable(self) -> Dict[str, Any]:
        """Return a JSON-serialisable mapping for on-disk storage."""

        payload = asdict(self)
        payload["occurred_at"] = self.occurred_at.isoformat()
        return payload


def _events_path() -> Path:
    """Return the path of the analytics event log, creating directories."""

    paths = resolve_paths(config.repo_root, config.accounts_root)
    analytics_dir = paths.repo_root / "data" / "analytics"
    analytics_dir.mkdir(parents=True, exist_ok=True)
    return analytics_dir / "events.jsonl"


def append_event(event: AnalyticsEvent) -> None:
    """Append ``event`` to the analytics log atomically."""

    path = _events_path()
    payload = event.as_serialisable()
    with _LOCK:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_events(source: str | None = None) -> List[AnalyticsEvent]:
    """Return all stored events, optionally filtered by ``source``."""

    path = _events_path()
    if not path.exists():
        return []

    events: List[AnalyticsEvent] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue

            occurred_raw = raw.get("occurred_at")
            try:
                occurred_at = (
                    datetime.fromisoformat(occurred_raw)
                    if isinstance(occurred_raw, str)
                    else datetime.now(timezone.utc)
                )
            except ValueError:
                occurred_at = datetime.now(timezone.utc)

            evt = AnalyticsEvent(
                source=str(raw.get("source", "")),
                event=str(raw.get("event", "")),
                user=raw.get("user"),
                metadata=raw.get("metadata") if isinstance(raw.get("metadata"), dict) else None,
                occurred_at=occurred_at,
            )
            if source is None or evt.source == source:
                events.append(evt)

    return events


def iter_events() -> Iterator[AnalyticsEvent]:
    """Yield all events lazily (used by tests)."""

    for event in load_events():
        yield event


def clear_events() -> None:
    """Remove any stored analytics events (used by tests)."""

    path = _events_path()
    if path.exists():
        with _LOCK:
            path.unlink()

