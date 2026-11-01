"""Per-user "last visit" timestamps for the since-last-visit digest (#11195).

The dashboard's "Since you were last here" card (#7835) compares against the
viewer's previous visit to a group. That used to live in ``localStorage``, so
it was per browser profile rather than per user. Each signed-in user now has
one small JSON document holding a record per group slug:

``{base}/{user}.json`` -> ``{"version", "updated_at", "groups": {slug: {"previous", "current"}}}``

Timestamps are UTC ISO 8601 instants taken from the server clock. ``{user}``
is the SHA-256 of the lower-cased email, as for saved watchlists, so no key or
file name carries the address.

``{base}`` is ``LAST_VISIT_STORAGE_URI`` when set, else
``s3://$DATA_BUCKET/watchlists/last_visit`` on AWS, else
``{data_root}/last_visit`` locally. On AWS it sits under the ``watchlists/``
prefix on purpose: the backend Lambda already has GetObject/PutObject and,
crucially, ListBucket there, so a not-yet-written document reads as a 404
("first visit") rather than a 403. A prefix of its own would need a new
ListBucket grant in ``cdk/`` first. The store implementation (file and S3,
with conditional writes) is shared with :mod:`backend.common.watchlists` for
the same reason.

Multi-device semantics are deliberately simple: one record per user and
group, advanced by a visit from any device. A visit within
``VISIT_SESSION_GAP`` of the last one keeps the previous visit (a reload or a
second tab does not reset the comparison); after the gap, the last visit
becomes the previous one. This mirrors ``advanceVisitRecord`` in
``frontend/src/lib/sinceLastVisit.ts``.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.common.watchlists import S3_PREFIX as WATCHLISTS_S3_PREFIX
from backend.common.watchlists import (
    WatchlistsStore,
    WatchlistsUnavailable,
    _PreconditionFailed,
    _Stored,
    store_from_uri,
    user_key,
)
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

DOCUMENT_VERSION = 1
S3_PREFIX = f"{WATCHLISTS_S3_PREFIX}/last_visit"
VISIT_SESSION_GAP = timedelta(hours=1)
# Groups kept per user; the least recently visited are dropped beyond this.
MAX_GROUPS = 50
# A conditional write that loses to a concurrent visit is retried this often.
_WRITE_ATTEMPTS = 3


class LastVisitUnavailable(Exception):
    """The store could not be read or written, or holds a damaged document."""


@dataclass(frozen=True)
class VisitRecord:
    previous: Optional[datetime]
    current: datetime

    def public(self) -> Dict[str, Optional[str]]:
        return {
            "previous": self.previous.isoformat() if self.previous else None,
            "current": self.current.isoformat(),
        }


def _default_uri() -> str:
    explicit = os.getenv("LAST_VISIT_STORAGE_URI", "").strip()
    if explicit:
        return explicit
    bucket = os.getenv("DATA_BUCKET", "").strip()
    if bucket:
        return f"s3://{bucket}/{S3_PREFIX}"
    root = config.data_root or Path(__file__).resolve().parents[2] / "data"
    return str(Path(root) / "last_visit")


def get_last_visit_store() -> WatchlistsStore:
    return store_from_uri(_default_uri())


def _object_key(email: str) -> str:
    return f"{user_key(email)}.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_instant(value: Any) -> Optional[datetime]:
    """A timezone-aware UTC datetime from an ISO 8601 string, else ``None``."""

    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _record_from(raw: Any) -> Optional[VisitRecord]:
    """A stored or seeded record; a malformed one is ``None`` (a first visit)."""

    if not isinstance(raw, dict):
        return None
    current = _parse_instant(raw.get("current"))
    if current is None:
        return None
    previous = _parse_instant(raw.get("previous"))
    if previous is not None and previous > current:
        previous = None
    return VisitRecord(previous=previous, current=current)


def advance(record: Optional[VisitRecord], now: datetime) -> VisitRecord:
    """Advance ``record`` to ``now``, keeping the previous visit within the session gap."""

    if record is None:
        return VisitRecord(previous=None, current=now)
    if now - record.current < VISIT_SESSION_GAP:
        return VisitRecord(previous=record.previous, current=now)
    return VisitRecord(previous=record.current, current=now)


def _decode(stored: Optional[_Stored]) -> Dict[str, Any]:
    """The ``groups`` map; empty when nothing is saved yet."""

    if stored is None:
        return {}
    try:
        doc = json.loads(stored.data)
    except json.JSONDecodeError as exc:
        raise LastVisitUnavailable("Stored last-visit document is not valid JSON") from exc
    groups = doc.get("groups") if isinstance(doc, dict) else None
    if not isinstance(groups, dict):
        # Never overwrite a document this module did not write: other groups'
        # records would be lost along with it.
        raise LastVisitUnavailable("Stored last-visit document is malformed")
    return groups


def _trim(groups: Dict[str, Any]) -> Dict[str, Any]:
    if len(groups) <= MAX_GROUPS:
        return groups

    def last_seen(item: tuple[str, Any]) -> datetime:
        record = _record_from(item[1])
        return record.current if record else datetime.min.replace(tzinfo=timezone.utc)

    newest = sorted(groups.items(), key=last_seen, reverse=True)[:MAX_GROUPS]
    return dict(newest)


def _update(
    email: str,
    slug: str,
    change: Callable[[Optional[VisitRecord]], VisitRecord],
    store: Optional[WatchlistsStore],
) -> VisitRecord:
    store = store or get_last_visit_store()
    key = _object_key(email)
    try:
        for _ in range(_WRITE_ATTEMPTS):
            stored = store.read(key)
            groups = _decode(stored)
            record = change(_record_from(groups.get(slug)))
            groups[slug] = record.public()
            body = {"version": DOCUMENT_VERSION, "updated_at": _now().isoformat(), "groups": _trim(groups)}
            try:
                store.write(key, json.dumps(body, indent=2).encode("utf-8"), expect_tag=stored.tag if stored else None)
            except _PreconditionFailed:
                continue
            return record
    except WatchlistsUnavailable as exc:
        raise LastVisitUnavailable(str(exc)) from exc
    logger.warning("Last-visit write for %s kept losing to concurrent visits", sanitise_log_value(slug))
    raise LastVisitUnavailable("Last-visit document kept changing during the write")


def record_visit(
    email: str,
    slug: str,
    *,
    seed: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
    store: Optional[WatchlistsStore] = None,
) -> VisitRecord:
    """Record a visit to ``slug`` by ``email`` and return the advanced record.

    ``seed`` is the browser's old ``localStorage`` record (``previous`` and
    ``current`` as ISO instants). It is used only when nothing is stored for
    the group yet, so moving to server-side storage does not cost anyone the
    digest on their first visit after the change. A seed from the future is
    ignored.
    """

    at = now or _now()

    def change(existing: Optional[VisitRecord]) -> VisitRecord:
        if existing is None and seed is not None:
            seeded = _record_from(seed)
            if seeded is not None and seeded.current <= at:
                existing = seeded
        return advance(existing, at)

    return _update(email, slug, change, store)


def dismiss_visit(
    email: str,
    slug: str,
    *,
    now: Optional[datetime] = None,
    store: Optional[WatchlistsStore] = None,
) -> VisitRecord:
    """Mark everything up to now as seen for ``slug`` (the digest was dismissed).

    ``previous`` is cleared so a reload within the session keeps the card
    hidden; after the session gap this visit becomes the previous one.
    """

    at = now or _now()
    return _update(email, slug, lambda _existing: VisitRecord(previous=None, current=at), store)


__all__ = [
    "LastVisitUnavailable",
    "MAX_GROUPS",
    "VISIT_SESSION_GAP",
    "VisitRecord",
    "advance",
    "dismiss_visit",
    "get_last_visit_store",
    "record_visit",
    "user_key",
]
