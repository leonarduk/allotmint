"""Per-user storage for the chat conversation tree (#8870).

Each user has one current conversation plus the conversations archived by
"New chat", stored under a per-user prefix of ``CHAT_HISTORY_STORAGE_URI``:

``{base}/{user}/current.json``             the conversation the panel shows
``{base}/{user}/archive/r{revision}.json`` one per "New chat"

``{user}`` is the SHA-256 of the lower-cased email, so neither object keys nor
file names carry the address. ``{base}`` is ``s3://bucket/prefix`` in Lambda
and defaults to ``{data_root}/chat`` locally.

This deliberately does not use :func:`backend.common.storage.get_storage`:
those backends return ``{}`` on any read failure, which here would turn an S3
outage into "no conversation, revision 0" and let the next save overwrite the
real one. Every failure below raises :class:`ChatHistoryUnavailable` instead.

Writes are optimistic: the document carries a ``revision`` and a save based
on an older one raises :class:`ChatConversationConflict`. On S3 the check is
made atomic with conditional writes (``IfMatch``/``IfNoneMatch``), so two
devices saving at once cannot both win.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Protocol
from urllib.parse import urlparse

from botocore.exceptions import BotoCoreError, ClientError

from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

DOCUMENT_VERSION = 1
CURRENT_NAME = "current.json"
ARCHIVE_DIR = "archive"
# Archiving retries when another write lands between its read and its write.
_ARCHIVE_ATTEMPTS = 3


class ChatHistoryUnavailable(Exception):
    """The store could not be read or written."""


class ChatConversationConflict(Exception):
    """A save was based on a revision that is no longer current."""

    def __init__(self, current: Dict[str, Any]):
        super().__init__("Chat conversation was changed elsewhere")
        self.current = current


class _PreconditionFailed(Exception):
    """A conditional write lost to a concurrent write."""


@dataclass(frozen=True)
class _Stored:
    data: bytes
    tag: str


class ChatStore(Protocol):
    def read(self, key: str) -> Optional[_Stored]:
        """Return the object at ``key``, or ``None`` if it does not exist."""

    def write(self, key: str, data: bytes, *, expect_tag: Optional[str]) -> None:
        """Write ``key`` if its tag is still ``expect_tag`` (``None``: it must not exist)."""

    def write_new(self, key: str, data: bytes) -> None:
        """Write ``key`` unconditionally."""

    def delete_prefix(self, prefix: str) -> int:
        """Delete every object under ``prefix``; return how many."""


@dataclass
class FileChatStore:
    """Local-file store for development; one lock serialises the conditional writes."""

    root: Path
    _lock = threading.Lock()

    def _path(self, key: str) -> Path:
        return self.root / key

    @staticmethod
    def _tag(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def read(self, key: str) -> Optional[_Stored]:
        try:
            data = self._path(key).read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ChatHistoryUnavailable(str(exc)) from exc
        return _Stored(data, self._tag(data))

    def write(self, key: str, data: bytes, *, expect_tag: Optional[str]) -> None:
        with self._lock:
            existing = self.read(key)
            if (existing.tag if existing else None) != expect_tag:
                raise _PreconditionFailed()
            self.write_new(key, data)

    def write_new(self, key: str, data: bytes) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            raise ChatHistoryUnavailable(str(exc)) from exc

    def delete_prefix(self, prefix: str) -> int:
        base = self._path(prefix)
        if not base.is_dir():
            return 0
        deleted = 0
        try:
            for path in sorted(base.rglob("*"), reverse=True):
                if path.is_dir():
                    path.rmdir()
                else:
                    path.unlink()
                    deleted += 1
            base.rmdir()
        except OSError as exc:
            raise ChatHistoryUnavailable(str(exc)) from exc
        return deleted


@dataclass
class S3ChatStore:
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

    def _unavailable(self, action: str, key: str, exc: Exception) -> ChatHistoryUnavailable:
        logger.warning(
            "Chat history S3 %s failed for %s/%s: %s",
            sanitise_log_value(action),
            sanitise_log_value(self.bucket),
            sanitise_log_value(self._key(key)),
            sanitise_log_value(exc),
        )
        return ChatHistoryUnavailable(f"S3 {action} failed")

    def read(self, key: str) -> Optional[_Stored]:
        try:
            obj = self._client().get_object(Bucket=self.bucket, Key=self._key(key))
            return _Stored(obj["Body"].read(), obj["ETag"])
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                return None
            raise self._unavailable("read", key, exc) from exc
        except BotoCoreError as exc:
            raise self._unavailable("read", key, exc) from exc

    def write(self, key: str, data: bytes, *, expect_tag: Optional[str]) -> None:
        condition = {"IfMatch": expect_tag} if expect_tag else {"IfNoneMatch": "*"}
        self._put(key, data, condition)

    def write_new(self, key: str, data: bytes) -> None:
        self._put(key, data, {})

    def _put(self, key: str, data: bytes, condition: Dict[str, str]) -> None:
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
            if condition and code in {"PreconditionFailed", "ConditionalRequestConflict"}:
                raise _PreconditionFailed() from exc
            raise self._unavailable("write", key, exc) from exc
        except BotoCoreError as exc:
            raise self._unavailable("write", key, exc) from exc

    def delete_prefix(self, prefix: str) -> int:
        client = self._client()
        deleted = 0
        try:
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=self._key(prefix)):
                keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if keys:
                    client.delete_objects(Bucket=self.bucket, Delete={"Objects": keys, "Quiet": True})
                    deleted += len(keys)
        except (ClientError, BotoCoreError) as exc:
            raise self._unavailable("delete", prefix, exc) from exc
        return deleted


def store_from_uri(uri: str) -> ChatStore:
    """Return the store for a ``s3://bucket/prefix`` or ``file://`` / plain path base."""

    parsed = urlparse(uri)
    if parsed.scheme == "s3":
        return S3ChatStore(bucket=parsed.netloc, prefix=parsed.path.strip("/"))
    if parsed.scheme in {"file", ""}:
        path = os.path.join(parsed.netloc, parsed.path.lstrip("/")) if parsed.netloc else parsed.path
        return FileChatStore(root=Path(path))
    raise ValueError(f"Unsupported chat history storage scheme: {parsed.scheme}")


def _default_uri() -> str:
    root = config.data_root or Path(__file__).resolve().parents[2] / "data"
    return str(Path(root) / "chat")


def get_chat_store() -> ChatStore:
    return store_from_uri(os.environ.get("CHAT_HISTORY_STORAGE_URI") or _default_uri())


def user_key(email: str) -> str:
    """Return the storage id for ``email``: a hash, so the address never reaches a key."""

    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def empty_conversation() -> Dict[str, Any]:
    return {"nodes": [], "active": {}, "nextId": 1}


def _document(revision: int, conversation: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "version": DOCUMENT_VERSION,
        "revision": revision,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "conversation": conversation,
    }


def _decode(stored: Optional[_Stored]) -> Dict[str, Any]:
    if stored is None:
        return _document(0, empty_conversation())
    try:
        doc = json.loads(stored.data)
    except json.JSONDecodeError as exc:
        raise ChatHistoryUnavailable("Stored chat conversation is not valid JSON") from exc
    revision = doc.get("revision") if isinstance(doc, dict) else None
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ChatHistoryUnavailable("Stored chat conversation is malformed")
    return doc


def _public(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {"revision": doc["revision"], "conversation": doc.get("conversation") or empty_conversation()}


def _current_key(user: str) -> str:
    return f"{user}/{CURRENT_NAME}"


def load_conversation(email: str, store: Optional[ChatStore] = None) -> Dict[str, Any]:
    """Return ``{"revision", "conversation"}`` for ``email``; revision 0 when none is stored."""

    store = store or get_chat_store()
    return _public(_decode(store.read(_current_key(user_key(email)))))


def save_conversation(
    email: str,
    conversation: Dict[str, Any],
    base_revision: int,
    store: Optional[ChatStore] = None,
) -> int:
    """Replace the conversation if it is still at ``base_revision``; return the new revision.

    Raises:
        ChatConversationConflict: the stored revision is not ``base_revision``.
    """

    store = store or get_chat_store()
    key = _current_key(user_key(email))
    stored = store.read(key)
    current = _decode(stored)
    if current["revision"] != base_revision:
        raise ChatConversationConflict(_public(current))
    revision = base_revision + 1
    body = json.dumps(_document(revision, conversation)).encode("utf-8")
    try:
        store.write(key, body, expect_tag=stored.tag if stored else None)
    except _PreconditionFailed:
        raise ChatConversationConflict(_public(_decode(store.read(key)))) from None
    return revision


def archive_conversation(email: str, store: Optional[ChatStore] = None) -> Dict[str, Any]:
    """Move the current conversation to the archive and start an empty one.

    Archives whatever is current, whichever device wrote it, so nothing is
    lost to a race. An empty conversation is not archived.
    Returns ``{"revision", "archived"}``.
    """

    store = store or get_chat_store()
    user = user_key(email)
    key = _current_key(user)
    for _ in range(_ARCHIVE_ATTEMPTS):
        stored = store.read(key)
        current = _decode(stored)
        if stored is None or not (current.get("conversation") or {}).get("nodes"):
            return {"revision": current["revision"], "archived": False}
        # Named by revision, so a retry after a failed write below rewrites
        # the same archive rather than adding a duplicate.
        store.write_new(f"{user}/{ARCHIVE_DIR}/r{current['revision']:08d}.json", stored.data)
        revision = current["revision"] + 1
        body = json.dumps(_document(revision, empty_conversation())).encode("utf-8")
        try:
            store.write(key, body, expect_tag=stored.tag)
        except _PreconditionFailed:
            # Changed after the copy: archive the newer version on the next pass.
            continue
        return {"revision": revision, "archived": True}
    raise ChatHistoryUnavailable("Chat conversation kept changing while being archived")


def delete_history(email: str, store: Optional[ChatStore] = None) -> int:
    """Delete the current conversation and every archived one; return how many objects."""

    store = store or get_chat_store()
    return store.delete_prefix(f"{user_key(email)}/")


__all__ = [
    "ChatConversationConflict",
    "ChatHistoryUnavailable",
    "ChatStore",
    "FileChatStore",
    "S3ChatStore",
    "archive_conversation",
    "delete_history",
    "empty_conversation",
    "get_chat_store",
    "load_conversation",
    "save_conversation",
    "store_from_uri",
    "user_key",
]
