"""Routes for scenario events."""

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from backend.config import config
from backend.logging_setup import sanitise_log_value

router = APIRouter(tags=["events"])
logger = logging.getLogger(__name__)

# Repo-bundled catalogue, used when ``data_root`` (commonly a separate
# user-data checkout such as ``../allotmint-data``) provides no events file.
_BUNDLED_EVENTS_PATH = Path(__file__).resolve().parents[2] / "data" / "events.json"


def _resolve_events_path() -> Path:
    if config.data_root:
        for rel in ("events/market_events.json", "events.json"):
            candidate = config.data_root / rel
            if candidate.is_file():
                return candidate
    return _BUNDLED_EVENTS_PATH


def _market_event(event: dict[str, Any]) -> dict[str, str]:
    return {"id": event["date"], "name": f"{event['date']}: {event['description']}"}


def _normalise_events(raw: Any) -> list[dict[str, str]]:
    """Return ``[{id, name}]`` from either supported events file layout.

    * flat list: ``[{"id": ..., "name": ...}]`` (``data/events.json``)
    * market events: ``{"events": [{"date": ..., "description": ...}]}``
      (``events/market_events.json``); the date doubles as the event id.
    """
    if isinstance(raw, dict):
        return [_market_event(e) for e in raw.get("events", [])]
    return [{"id": e["id"], "name": e["name"]} for e in raw]


_events_path = globals().get("_events_path") or _resolve_events_path()

try:
    with _events_path.open() as fh:
        _EVENTS = _normalise_events(json.load(fh))
except FileNotFoundError:
    logger.warning(
        "Scenario events file not found at %s; no events will be offered",
        sanitise_log_value(_events_path),
    )
    _EVENTS = []
except (OSError, ValueError, KeyError, TypeError) as exc:
    # A malformed catalogue must not take down the whole app at import time.
    logger.error(
        "Scenario events file %s is unreadable or malformed (%s); no events will be offered",
        sanitise_log_value(_events_path),
        sanitise_log_value(exc),
    )
    _EVENTS = []


@router.get("/events")
def list_events():
    """Return configured scenario events."""
    return _EVENTS
