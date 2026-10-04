"""Per-user storage for the chat conversation tree (#8870).

Each user has one current conversation plus the conversations archived by
"New chat", stored under a per-user prefix of ``CHAT_HISTORY_STORAGE_URI``:

``{base}/{user}/current.json``             the conversation the panel shows
``{base}/{user}/archive/r{revision}.json`` one per "New chat"

Each document may carry a user-given ``title``; without one, lists name a
conversation after its first question. Archived conversations can be listed,
renamed, deleted one at a time, or reopened as the current one.

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
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple
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
# The id lists use for the current conversation; archived ones are r{revision}.
CURRENT_ID = "current"
_ARCHIVE_ID = re.compile(r"r\d{8}")
MAX_TITLE_CHARS = 120
# A conversation without a title is listed under its first question, cut to this.
_DERIVED_TITLE_CHARS = 60
# The most archived conversations listed, newest first.
MAX_LISTED = 100


class ChatHistoryUnavailable(Exception):
    """The store could not be read or written."""


class ChatConversationNotFound(Exception):
    """No saved conversation has that id."""


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

    def list_keys(self, prefix: str) -> List[str]:
        """Return the keys of every object under ``prefix``, relative to the store."""

    def delete(self, key: str) -> None:
        """Delete ``key``; a missing key is not an error."""


@dataclass
class FileChatStore:
    """Local-file store for development; one lock serialises the conditional writes."""

    root: Path
    # Class-wide on purpose: get_chat_store() builds a new store per request,
    # so a per-instance lock would serialise nothing. One process only, which
    # is all the local dev server runs; Lambda uses S3ChatStore.
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

    def list_keys(self, prefix: str) -> List[str]:
        base = self._path(prefix)
        if not base.is_dir():
            return []
        try:
            return [p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file()]
        except OSError as exc:
            raise ChatHistoryUnavailable(str(exc)) from exc

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError as exc:
            raise ChatHistoryUnavailable(str(exc)) from exc


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
                    resp = client.delete_objects(Bucket=self.bucket, Delete={"Objects": keys, "Quiet": True})
                    # Per-key failures come back in the response, not as an
                    # exception; a partial delete must not report success.
                    if resp.get("Errors"):
                        raise ChatHistoryUnavailable(f"S3 failed to delete {len(resp['Errors'])} chat object(s)")
                    deleted += len(keys)
        except (ClientError, BotoCoreError) as exc:
            raise self._unavailable("delete", prefix, exc) from exc
        return deleted

    def list_keys(self, prefix: str) -> List[str]:
        start = len(self._key(""))
        keys: List[str] = []
        try:
            paginator = self._client().get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=self._key(prefix)):
                keys.extend(obj["Key"][start:] for obj in page.get("Contents", []))
        except (ClientError, BotoCoreError) as exc:
            raise self._unavailable("list", prefix, exc) from exc
        return keys

    def delete(self, key: str) -> None:
        try:
            self._client().delete_object(Bucket=self.bucket, Key=self._key(key))
        except (ClientError, BotoCoreError) as exc:
            raise self._unavailable("delete", key, exc) from exc


def store_from_uri(uri: str) -> ChatStore:
    """Return the store for a ``s3://bucket/prefix`` or ``file://`` / plain path base."""

    parsed = urlparse(uri)
    if parsed.scheme == "s3":
        return S3ChatStore(bucket=parsed.netloc, prefix=parsed.path.strip("/"))
    # A Windows path such as D:\data\chat parses as scheme "d".
    if len(parsed.scheme) == 1:
        return FileChatStore(root=Path(uri))
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


def _document(revision: int, conversation: Dict[str, Any], title: Optional[str] = None) -> Dict[str, Any]:
    doc = {
        "version": DOCUMENT_VERSION,
        "revision": revision,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "conversation": conversation,
    }
    if title:
        doc["title"] = title
    return doc


def _encode(doc: Dict[str, Any]) -> bytes:
    return json.dumps(doc).encode("utf-8")


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
    conversation = doc.get("conversation")
    # Only this module writes these documents, and always with a tree, so a
    # missing or damaged one is an error: it must not read as an empty
    # conversation that the next save would then overwrite.
    if not (
        isinstance(conversation, dict)
        and isinstance(conversation.get("nodes", []), list)
        and isinstance(conversation.get("active", {}), dict)
    ):
        raise ChatHistoryUnavailable("Stored chat conversation is malformed")
    return doc


def _public(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {"revision": doc["revision"], "conversation": doc.get("conversation") or empty_conversation()}


def _title(doc: Dict[str, Any]) -> Optional[str]:
    title = doc.get("title")
    return title if isinstance(title, str) and title else None


def _has_messages(doc: Dict[str, Any]) -> bool:
    return bool((doc.get("conversation") or {}).get("nodes"))


def _derived_title(conversation: Dict[str, Any]) -> str:
    """The first question, on one line and cut short: a name for an untitled conversation."""

    for node in conversation.get("nodes", []):
        if isinstance(node, dict) and node.get("role") == "user" and isinstance(node.get("content"), str):
            text = " ".join(node["content"].split())
            if text:
                cut = _DERIVED_TITLE_CHARS
                return text if len(text) <= cut else text[: cut - 1].rstrip() + "\u2026"
    return "Untitled chat"


def _summary(chat_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    conversation = doc.get("conversation") or empty_conversation()
    title = _title(doc)
    return {
        "id": chat_id,
        "title": title or _derived_title(conversation),
        "named": title is not None,
        "updated_at": doc.get("updated_at"),
        "messages": len(conversation.get("nodes", [])),
    }


def _key_for(user: str, chat_id: str) -> str:
    """The storage key of ``chat_id``; anything but ``current`` or ``r########`` is not found."""

    if chat_id == CURRENT_ID:
        return _current_key(user)
    if _ARCHIVE_ID.fullmatch(chat_id):
        return f"{user}/{ARCHIVE_DIR}/{chat_id}.json"
    raise ChatConversationNotFound(chat_id)


def clean_title(title: str) -> Optional[str]:
    """``title`` on one line and at most ``MAX_TITLE_CHARS``, or ``None`` when blank (clearing the name)."""

    return " ".join(title.split())[:MAX_TITLE_CHARS].rstrip() or None


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
    *,
    title: Optional[str] = None,
) -> int:
    """Replace the conversation if it is still at ``base_revision``; return the new revision.

    ``title`` names it; ``None`` keeps the name it already has.

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
    # The name given to this conversation stays with it across saves.
    title = _title(current) if title is None else title
    body = _encode(_document(revision, conversation, title))
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
        if stored is None or not _has_messages(current):
            return {"revision": current["revision"], "archived": False}
        # Named by revision, so a retry after a failed write below rewrites
        # the same archive rather than adding a duplicate.
        store.write_new(f"{user}/{ARCHIVE_DIR}/r{current['revision']:08d}.json", stored.data)
        revision = current["revision"] + 1
        body = _encode(_document(revision, empty_conversation()))
        try:
            store.write(key, body, expect_tag=stored.tag)
        except _PreconditionFailed:
            # Changed after the copy: archive the newer version on the next pass.
            continue
        return {"revision": revision, "archived": True}
    raise ChatHistoryUnavailable("Chat conversation kept changing while being archived")


def list_conversations(email: str, store: Optional[ChatStore] = None) -> List[Dict[str, Any]]:
    """Summaries of the current conversation (unless empty) then the archived ones, newest first.

    Each is ``{"id", "title", "named", "updated_at", "messages"}``; ``named`` is
    false when the title was derived from the first question.
    """

    store = store or get_chat_store()
    user = user_key(email)
    summaries: List[Dict[str, Any]] = []
    current = _decode(store.read(_current_key(user)))
    if _has_messages(current):
        summaries.append(_summary(CURRENT_ID, current))
    prefix = f"{user}/{ARCHIVE_DIR}/"
    names = (key[len(prefix) :].removesuffix(".json") for key in store.list_keys(prefix))
    for chat_id in sorted((n for n in names if _ARCHIVE_ID.fullmatch(n)), reverse=True)[:MAX_LISTED]:
        stored = store.read(_key_for(user, chat_id))
        if stored is not None:  # None: deleted since it was listed
            summaries.append(_summary(chat_id, _decode(stored)))
    return summaries


def _read_archived(store: ChatStore, user: str, chat_id: str) -> Tuple[str, Dict[str, Any]]:
    if chat_id == CURRENT_ID:
        raise ChatConversationNotFound(chat_id)
    key = _key_for(user, chat_id)
    stored = store.read(key)
    if stored is None:
        raise ChatConversationNotFound(chat_id)
    return key, _decode(stored)


def rename_conversation(email: str, chat_id: str, title: Optional[str], store: Optional[ChatStore] = None) -> None:
    """Name ``chat_id`` (``current`` or an archived id); ``None`` clears the name.

    Renaming the current conversation keeps its revision, so a tab's next
    save still applies, and that save keeps the new name.
    """

    store = store or get_chat_store()
    key = _key_for(user_key(email), chat_id)
    for _ in range(_ARCHIVE_ATTEMPTS):
        stored = store.read(key)
        doc = _decode(stored)
        if stored is None or not _has_messages(doc):
            raise ChatConversationNotFound(chat_id)
        doc.pop("title", None)
        if title:
            doc["title"] = title
        try:
            store.write(key, _encode(doc), expect_tag=stored.tag)
        except _PreconditionFailed:
            continue
        return
    raise ChatHistoryUnavailable("Chat conversation kept changing while being renamed")


def delete_conversation(email: str, chat_id: str, store: Optional[ChatStore] = None) -> None:
    """Delete one archived conversation. The current one is put away with "New chat" instead."""

    store = store or get_chat_store()
    key, _ = _read_archived(store, user_key(email), chat_id)
    store.delete(key)


def open_conversation(email: str, chat_id: str, store: Optional[ChatStore] = None) -> Dict[str, Any]:
    """Make archived ``chat_id`` the current conversation, archiving the current one first.

    Returns ``{"revision", "conversation", "title"}`` of the new current one.

    Raises:
        ChatConversationConflict: another tab or device saved between the archive and the write.
    """

    store = store or get_chat_store()
    key, doc = _read_archived(store, user_key(email), chat_id)
    revision = archive_conversation(email, store)["revision"]
    conversation = doc.get("conversation") or empty_conversation()
    title = _title(doc)
    revision = save_conversation(email, conversation, revision, store, title=title)
    # Now current, so drop the archived copy; the next "New chat" archives it again.
    store.delete(key)
    return {"revision": revision, "conversation": conversation, "title": title}


def delete_history(email: str, store: Optional[ChatStore] = None) -> int:
    """Delete the current conversation and every archived one; return how many objects."""

    store = store or get_chat_store()
    return store.delete_prefix(f"{user_key(email)}/")


__all__ = [
    "CURRENT_ID",
    "ChatConversationConflict",
    "ChatConversationNotFound",
    "ChatHistoryUnavailable",
    "ChatStore",
    "FileChatStore",
    "S3ChatStore",
    "archive_conversation",
    "clean_title",
    "delete_conversation",
    "delete_history",
    "empty_conversation",
    "get_chat_store",
    "list_conversations",
    "load_conversation",
    "open_conversation",
    "rename_conversation",
    "save_conversation",
    "store_from_uri",
    "user_key",
]
