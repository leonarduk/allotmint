"""Routes for scenario events."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter

from backend.config import config

router = APIRouter(tags=["events"])
logger = logging.getLogger(__name__)

# The event catalogue is reference data shipped with the repo. ``data_root``
# commonly points at a separate user-data checkout (e.g. ``../allotmint-data``)
# that has no ``events.json``, so fall back to the bundled copy rather than
# serving an empty list.
_BUNDLED_EVENTS_PATH = Path(__file__).resolve().parents[2] / "data" / "events.json"


def _resolve_events_path() -> Path:
    if config.data_root:
        candidate = config.data_root / "events.json"
        if candidate.exists():
            return candidate
    return _BUNDLED_EVENTS_PATH


_events_path = globals().get("_events_path") or _resolve_events_path()

try:
    with _events_path.open() as fh:
        _EVENTS = [{"id": e["id"], "name": e["name"]} for e in json.load(fh)]
except FileNotFoundError:
    logger.warning("Scenario events file not found at %s; no events will be offered", _events_path)
    _EVENTS = []


@router.get("/events")
def list_events():
    """Return configured scenario events."""
    return _EVENTS
