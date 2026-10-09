"""Stored digests: ``<location>/<owner>/<YYYY-MM-DD>.json`` plus ``latest.json`` (#10485).

The location is ``BOTS_DIGESTS_URI`` when set (deployed: ``s3://<bucket>/bots/digests``),
otherwise ``{data_root}/bots/digests``. ``index.json`` lists the stored dates,
newest first, so history needs no bucket listing. A later digest on the same
day replaces that day's file. These are the only records the digest writes.
"""

from __future__ import annotations

from typing import List, Optional

from backend.bots.digest_models import Digest
from backend.bots.storage import json_storage, location

DIGESTS_URI_ENV = "BOTS_DIGESTS_URI"
LATEST_NAME = "latest.json"
INDEX_NAME = "index.json"
MAX_HISTORY = 104  # two years of weekly digests


def _base() -> str:
    return location(DIGESTS_URI_ENV, "bots/digests")


def _load_index(owner: str) -> List[str]:
    dates = json_storage(_base(), owner, INDEX_NAME).load().get("dates")
    return [str(d) for d in dates] if isinstance(dates, list) else []


def save_digest(digest: Digest) -> str:
    """Persist ``digest`` for its owner; return the date key it was saved under."""

    day = digest.generated_at.date().isoformat()
    payload = digest.model_dump(mode="json")
    json_storage(_base(), digest.owner, f"{day}.json").save(payload)
    json_storage(_base(), digest.owner, LATEST_NAME).save(payload)
    dates = [day] + [d for d in _load_index(digest.owner) if d != day]
    json_storage(_base(), digest.owner, INDEX_NAME).save({"dates": dates[:MAX_HISTORY]})
    return day


def load_latest(owner: str) -> Optional[Digest]:
    raw = json_storage(_base(), owner, LATEST_NAME).load()
    return Digest.model_validate(raw) if raw else None


def load_history(owner: str, limit: int = 8) -> List[Digest]:
    """Up to ``limit`` stored digests for ``owner``, newest first."""

    digests: List[Digest] = []
    for day in _load_index(owner)[: max(0, limit)]:
        raw = json_storage(_base(), owner, f"{day}.json").load()
        if raw:
            digests.append(Digest.model_validate(raw))
    return digests


__all__ = ["DIGESTS_URI_ENV", "load_history", "load_latest", "save_digest"]
