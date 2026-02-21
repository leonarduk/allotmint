"""Routes for scenario events."""

import json
from pathlib import Path
from fastapi import APIRouter
from backend.config import config

router = APIRouter(tags=["events"])

_events_path = globals().get("_events_path") or ((config.data_root / "events.json") if config.data_root else Path(__file__).resolve().parents[2] / "data" / "events.json")

try:
    with _events_path.open() as fh:
        _EVENTS = [{"id": e["id"], "name": e["name"]} for e in json.load(fh)]
except FileNotFoundError:
    _EVENTS = []


@router.get("/events")
def list_events():
    """Return configured scenario events."""
    return _EVENTS

