"""Timestamped research notes on an instrument, each tagged with a stance.

A note belongs to one user (the resolved identity, as for price triggers) and
one ticker. Notes are a journal: they can be added and deleted but not edited,
so the record of what was thought, and when, stays honest. The GBP price at
the time of writing is stored alongside so the page can show how the call has
played out since.

Persistence reuses the JSON storage abstraction (``file://``, ``s3://``,
``ssm://``) selected by ``INSTRUMENT_NOTES_URI``. When that is unset and
``DATA_BUCKET`` is, notes live in that bucket so Lambda deployments keep them
across cold starts.
"""

from __future__ import annotations

import math
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.common.storage import JSONStorage, get_storage
from backend.config import config

STANCES = ("bullish", "bearish", "neutral")
MAX_NOTE_LENGTH = 2000
MAX_NOTES_PER_USER = 1000

_S3_KEY = "research/instrument_notes.json"

_lock = threading.RLock()


class NoteError(ValueError):
    """The request was invalid (bad field, per-user limit)."""


class NoteNotFound(NoteError):
    """No note with the given id exists for that user."""


def _default_uri() -> str:
    explicit = os.getenv("INSTRUMENT_NOTES_URI")
    if explicit:
        return explicit
    bucket = os.getenv("DATA_BUCKET")
    if bucket:
        return f"s3://{bucket}/{_S3_KEY}"
    root = config.repo_root or Path(__file__).resolve().parents[1]
    return f"file://{root / 'data' / 'instrument_notes.json'}"


def _storage() -> JSONStorage:
    return get_storage(_default_uri())


def _load() -> Dict[str, Dict[str, Dict[str, Any]]]:
    data = _storage().load()
    return data if isinstance(data, dict) else {}


def _save(data: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
    _storage().save(data)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _clean_user(user: str) -> str:
    cleaned = (user or "").strip()
    if not cleaned:
        raise NoteError("user is required")
    return cleaned


def _clean_ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    if not ticker:
        raise NoteError("ticker is required")
    return ticker


def _clean_stance(value: Any) -> str:
    stance = str(value or "").strip().lower()
    if stance not in STANCES:
        raise NoteError(f"stance must be one of {', '.join(STANCES)}")
    return stance


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise NoteError("text is required")
    if len(text) > MAX_NOTE_LENGTH:
        raise NoteError(f"text must be at most {MAX_NOTE_LENGTH} characters")
    return text


def _clean_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError) as exc:
        raise NoteError("price must be a number") from exc
    if not math.isfinite(price) or price <= 0:
        raise NoteError("price must be a positive number")
    return price


def list_notes(user: str, ticker: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return ``user``'s notes, newest first, optionally for one ticker."""
    user = _clean_user(user)
    with _lock:
        rows = list(_load().get(user, {}).values())
    if ticker:
        wanted = _clean_ticker(ticker)
        rows = [r for r in rows if r["ticker"] == wanted]
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)


def create_note(
    user: str,
    *,
    ticker: Any,
    stance: Any,
    text: Any,
    price: Any = None,
) -> Dict[str, Any]:
    user = _clean_user(user)
    row: Dict[str, Any] = {
        "id": uuid.uuid4().hex[:12],
        "ticker": _clean_ticker(ticker),
        "stance": _clean_stance(stance),
        "text": _clean_text(text),
        "price": _clean_price(price),
        "created_at": _now(),
    }
    with _lock:
        data = _load()
        mine = data.setdefault(user, {})
        if len(mine) >= MAX_NOTES_PER_USER:
            raise NoteError(f"limit of {MAX_NOTES_PER_USER} notes per user reached")
        mine[row["id"]] = row
        _save(data)
    return row


def delete_note(user: str, note_id: str) -> Dict[str, Any]:
    user = _clean_user(user)
    with _lock:
        data = _load()
        row = data.get(user, {}).pop(note_id, None)
        if row is None:
            raise NoteNotFound(f"note {note_id!r} not found")
        if not data[user]:
            del data[user]
        _save(data)
    return row
