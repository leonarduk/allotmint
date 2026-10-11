"""Per-user storage for named watchlists (#10713).

Each user's watchlists are one JSON document, so they follow the user across
browsers and devices instead of living only in ``localStorage``:

``{base}/{user}.json``

``{user}`` is the SHA-256 of the lower-cased email (as for saved chats,
:mod:`backend.common.chat_history`), so neither object keys nor file names
carry the address. ``{base}`` is ``WATCHLISTS_STORAGE_URI`` when set, else
``s3://$DATA_BUCKET/watchlists`` on AWS, else ``{data_root}/watchlists``
locally -- i.e. inside the ``allotmint-data`` checkout when ``DATA_ROOT``
points at one.

The document holds the frontend's state as is (``activeId`` plus ``lists`` of
``{id, name, symbols}``, see ``frontend/src/lib/watchlistStore.ts``) with a
``revision``. Writes are optimistic: a save based on an older revision raises
:class:`WatchlistsConflict`, and on S3 the check is atomic through conditional
writes (``IfMatch``/``IfNoneMatch``), so two devices saving at once cannot
both win.

This does not use :func:`backend.common.storage.get_storage`: those backends
read any failure as ``{}``, which here would turn an S3 outage or a corrupt
file into "no watchlists" and let the next save overwrite the real ones.
Every such failure raises :class:`WatchlistsUnavailable` instead.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol
from urllib.parse import urlparse

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

DOCUMENT_VERSION = 1
S3_PREFIX = "watchlists"
MAX_LISTS = 50
# An S&P 500 copy (~500) fits twice over; see MAX_DOCUMENT_BYTES in the route.
MAX_SYMBOLS_PER_LIST = 1000
MAX_NAME_CHARS = 100
MAX_SYMBOL_CHARS = 40
# Ids the frontend makes: "default", or "wl-<time>-<random>".
_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
# A ticker such as ^FTSE, BT-A.L or USDGBP=X; never blank, spaced or comma-joined.
_SYMBOL_PATTERN = r"^[^\s,]+$"


class WatchlistsUnavailable(Exception):
    """The store could not be read or written, or holds a damaged document."""


class WatchlistsConflict(Exception):
    """A save was based on a revision that is no longer current."""

    def __init__(self, current: Dict[str, Any]):
        super().__init__("Watchlists were changed elsewhere")
        self.current = current


class _PreconditionFailed(Exception):
    """A conditional write lost to a concurrent write."""


class NamedWatchlist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_ID_PATTERN)
    name: str = Field(min_length=1, max_length=MAX_NAME_CHARS)
    symbols: List[str] = Field(default_factory=list, max_length=MAX_SYMBOLS_PER_LIST)

    @model_validator(mode="after")
    def _check(self) -> "NamedWatchlist":
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("a watchlist name cannot be blank")
        cleaned = [s.strip() for s in self.symbols]
        for symbol in cleaned:
            if not symbol or len(symbol) > MAX_SYMBOL_CHARS or any(c.isspace() or c == "," for c in symbol):
                raise ValueError(f"invalid symbol {symbol!r} in watchlist {self.name!r}")
        self.symbols = cleaned
        return self


class WatchlistsState(BaseModel):
    """The frontend's ``WatchlistsState``: every list plus the one on show."""

    model_config = ConfigDict(extra="forbid")

    activeId: str = Field(pattern=_ID_PATTERN)
    lists: List[NamedWatchlist] = Field(min_length=1, max_length=MAX_LISTS)

    @model_validator(mode="after")
    def _check(self) -> "WatchlistsState":
        ids = [w.id for w in self.lists]
        if len(set(ids)) != len(ids):
            raise ValueError("watchlist ids must be unique")
        names = [w.name.lower() for w in self.lists]
        if len(set(names)) != len(names):
            raise ValueError("watchlist names must be unique (ignoring case)")
        if self.activeId not in ids:
            raise ValueError("activeId must name one of the lists")
        return self


@dataclass(frozen=True)
class _Stored:
    data: bytes
    tag: str


class WatchlistsStore(Protocol):
    def read(self, key: str) -> Optional[_Stored]:
        """Return the object at ``key``, or ``None`` if it does not exist."""

    def write(self, key: str, data: bytes, *, expect_tag: Optional[str]) -> None:
        """Write ``key`` if its tag is still ``expect_tag`` (``None``: it must not exist)."""


@dataclass
class FileWatchlistsStore:
    """Local-file store; one lock serialises the conditional writes."""

    root: Path
    # Class-wide on purpose: get_watchlists_store() builds a store per request,
    # so a per-instance lock would serialise nothing. One process only, which
    # is all the local dev server runs; Lambda uses S3WatchlistsStore.
    _lock = threading.Lock()

    @staticmethod
    def _tag(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def read(self, key: str) -> Optional[_Stored]:
        try:
            data = (self.root / key).read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise WatchlistsUnavailable(str(exc)) from exc
        return _Stored(data, self._tag(data))

    def write(self, key: str, data: bytes, *, expect_tag: Optional[str]) -> None:
        with self._lock:
            existing = self.read(key)
            if (existing.tag if existing else None) != expect_tag:
                raise _PreconditionFailed()
            self._replace(self.root / key, data)

    @staticmethod
    def _replace(path: Path, data: bytes) -> None:
        """Write ``path`` atomically, so a crash never leaves a half-written document."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                os.replace(tmp, path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        except OSError as exc:
            raise WatchlistsUnavailable(str(exc)) from exc


@dataclass
class S3WatchlistsStore:
    bucket: str
    prefix: str
    client: Any | None = None

    def _client(self):
        if self.client is None:
            import boto3  # type: ignore

            self.client = boto3.client("s3")
        return self.client

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def _unavailable(self, action: str, key: str, exc: Exception) -> WatchlistsUnavailable:
        logger.warning(
            "Watchlists S3 %s failed for %s/%s: %s",
            sanitise_log_value(action),
            sanitise_log_value(self.bucket),
            sanitise_log_value(self._key(key)),
            sanitise_log_value(exc),
        )
        return WatchlistsUnavailable(f"S3 {action} failed")

    def read(self, key: str) -> Optional[_Stored]:
        try:
            obj = self._client().get_object(Bucket=self.bucket, Key=self._key(key))
            return _Stored(obj["Body"].read(), obj["ETag"])
        except ClientError as exc:
            # Without s3:ListBucket on the prefix a missing key is a 403, which
            # must not read as "nothing saved"; the Lambda is granted it.
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                return None
            raise self._unavailable("read", key, exc) from exc
        except BotoCoreError as exc:
            raise self._unavailable("read", key, exc) from exc

    def write(self, key: str, data: bytes, *, expect_tag: Optional[str]) -> None:
        condition = {"IfMatch": expect_tag} if expect_tag else {"IfNoneMatch": "*"}
        try:
            self._client().put_object(
                Bucket=self.bucket,
                Key=self._key(key),
                Body=data,
                ContentType="application/json",
                **condition,
            )
        except ClientError as exc:
            # 412: the object changed since it was read. 409: S3 reports a
            # conditional write racing another write to the same key.
            code = exc.response.get("Error", {}).get("Code")
            if code in {"PreconditionFailed", "ConditionalRequestConflict"}:
                raise _PreconditionFailed() from exc
            raise self._unavailable("write", key, exc) from exc
        except BotoCoreError as exc:
            raise self._unavailable("write", key, exc) from exc


def store_from_uri(uri: str) -> WatchlistsStore:
    """Return the store for a ``s3://bucket/prefix`` or ``file://`` / plain path base."""

    parsed = urlparse(uri)
    if parsed.scheme == "s3":
        return S3WatchlistsStore(bucket=parsed.netloc, prefix=parsed.path.strip("/"))
    # A Windows path such as D:\data\watchlists parses as scheme "d".
    if len(parsed.scheme) == 1:
        return FileWatchlistsStore(root=Path(uri))
    if parsed.scheme in {"file", ""}:
        path = os.path.join(parsed.netloc, parsed.path.lstrip("/")) if parsed.netloc else parsed.path
        return FileWatchlistsStore(root=Path(path))
    raise ValueError(f"Unsupported watchlists storage scheme: {parsed.scheme}")


def _default_uri() -> str:
    explicit = os.getenv("WATCHLISTS_STORAGE_URI", "").strip()
    if explicit:
        return explicit
    bucket = os.getenv("DATA_BUCKET", "").strip()
    if bucket:
        return f"s3://{bucket}/{S3_PREFIX}"
    root = config.data_root or Path(__file__).resolve().parents[2] / "data"
    return str(Path(root) / "watchlists")


def get_watchlists_store() -> WatchlistsStore:
    return store_from_uri(_default_uri())


def user_key(email: str) -> str:
    """Return the storage id for ``email``: a hash, so the address never reaches a key."""

    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _object_key(email: str) -> str:
    return f"{user_key(email)}.json"


def _document(revision: int, state: WatchlistsState) -> Dict[str, Any]:
    return {
        "version": DOCUMENT_VERSION,
        "revision": revision,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **state.model_dump(),
    }


def _public(revision: int, state: Optional[WatchlistsState]) -> Dict[str, Any]:
    return {"revision": revision, "state": state.model_dump() if state else None}


def _decode(stored: Optional[_Stored]) -> tuple[int, Optional[WatchlistsState]]:
    """``(revision, state)``; ``(0, None)`` when nothing is saved yet."""

    if stored is None:
        return 0, None
    try:
        doc = json.loads(stored.data)
    except json.JSONDecodeError as exc:
        raise WatchlistsUnavailable("Stored watchlists are not valid JSON") from exc
    revision = doc.get("revision") if isinstance(doc, dict) else None
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise WatchlistsUnavailable("Stored watchlists are malformed")
    try:
        state = WatchlistsState.model_validate({"activeId": doc.get("activeId"), "lists": doc.get("lists")})
    except ValidationError as exc:
        # Only this module writes these documents, and always valid, so a
        # damaged one is an error: it must not read as "no watchlists" that
        # the next save would then overwrite.
        raise WatchlistsUnavailable("Stored watchlists are malformed") from exc
    return revision, state


def load_watchlists(email: str, store: Optional[WatchlistsStore] = None) -> Dict[str, Any]:
    """Return ``{"revision", "state"}`` for ``email``; revision 0 and no state when none is saved."""

    store = store or get_watchlists_store()
    return _public(*_decode(store.read(_object_key(email))))


def save_watchlists(
    email: str,
    state: WatchlistsState,
    base_revision: int,
    store: Optional[WatchlistsStore] = None,
) -> int:
    """Replace the watchlists if they are still at ``base_revision``; return the new revision.

    Raises:
        WatchlistsConflict: the stored revision is not ``base_revision``.
    """

    store = store or get_watchlists_store()
    key = _object_key(email)
    stored = store.read(key)
    current_revision, current_state = _decode(stored)
    if current_revision != base_revision:
        raise WatchlistsConflict(_public(current_revision, current_state))
    revision = base_revision + 1
    body = json.dumps(_document(revision, state), indent=2).encode("utf-8")
    try:
        store.write(key, body, expect_tag=stored.tag if stored else None)
    except _PreconditionFailed:
        raise WatchlistsConflict(_public(*_decode(store.read(key)))) from None
    logger.info("Saved watchlists revision %s", sanitise_log_value(revision))
    return revision


__all__ = [
    "MAX_LISTS",
    "MAX_SYMBOLS_PER_LIST",
    "FileWatchlistsStore",
    "S3WatchlistsStore",
    "WatchlistsConflict",
    "WatchlistsState",
    "WatchlistsStore",
    "WatchlistsUnavailable",
    "get_watchlists_store",
    "load_watchlists",
    "save_watchlists",
    "store_from_uri",
    "user_key",
]
