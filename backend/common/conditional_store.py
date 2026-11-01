"""Per-key JSON document stores with conditional (compare-and-swap) writes.

Shared by :mod:`backend.common.watchlists` and :mod:`backend.common.last_visit`.
A store reads a key to a :class:`Stored` (bytes plus a tag) and writes a key
only if its tag is still the one the caller read; a lost race raises
:class:`PreconditionFailed`. On S3 the check is atomic through conditional
writes (``IfMatch``/``IfNoneMatch``); locally one process-wide lock serialises
the writes.

Unlike :func:`backend.common.storage.get_storage`, a failed read is never
reported as "nothing saved": every such failure raises the store's
``unavailable`` exception, so a caller cannot overwrite a document it could
not read. Subclasses set ``unavailable`` (and, for S3, ``label``) so each
feature keeps its own error type and log wording.
"""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Optional, Protocol, TypeVar
from urllib.parse import urlparse

from botocore.exceptions import BotoCoreError, ClientError

from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)


class StoreUnavailable(Exception):
    """The store could not be read or written."""


class PreconditionFailed(Exception):
    """A conditional write lost to a concurrent write."""


@dataclass(frozen=True)
class Stored:
    data: bytes
    tag: str


class ConditionalStore(Protocol):
    def read(self, key: str) -> Optional[Stored]:
        """Return the object at ``key``, or ``None`` if it does not exist."""

    def write(self, key: str, data: bytes, *, expect_tag: Optional[str]) -> None:
        """Write ``key`` if its tag is still ``expect_tag`` (``None``: it must not exist)."""


@dataclass
class FileStore:
    """Local-file store; one lock serialises the conditional writes."""

    root: Path
    unavailable: ClassVar[type[Exception]] = StoreUnavailable
    # Class-wide on purpose: callers build a store per request, so a
    # per-instance lock would serialise nothing. One process only, which is
    # all the local dev server runs; Lambda uses S3Store.
    _lock = threading.Lock()

    @staticmethod
    def _tag(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def read(self, key: str) -> Optional[Stored]:
        try:
            data = (self.root / key).read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise self.unavailable(str(exc)) from exc
        return Stored(data, self._tag(data))

    def write(self, key: str, data: bytes, *, expect_tag: Optional[str]) -> None:
        with self._lock:
            existing = self.read(key)
            if (existing.tag if existing else None) != expect_tag:
                raise PreconditionFailed()
            self._replace(self.root / key, data)

    def _replace(self, path: Path, data: bytes) -> None:
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
            raise self.unavailable(str(exc)) from exc


@dataclass
class S3Store:
    bucket: str
    prefix: str
    client: Any | None = None
    unavailable: ClassVar[type[Exception]] = StoreUnavailable
    # Names the feature in failure logs.
    label: ClassVar[str] = "Document store"

    def _client(self):
        if self.client is None:
            import boto3  # type: ignore

            self.client = boto3.client("s3")
        return self.client

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def _unavailable(self, action: str, key: str, exc: Exception) -> Exception:
        logger.warning(
            "%s S3 %s failed for %s/%s: %s",
            sanitise_log_value(self.label),
            sanitise_log_value(action),
            sanitise_log_value(self.bucket),
            sanitise_log_value(self._key(key)),
            sanitise_log_value(exc),
        )
        return self.unavailable(f"S3 {action} failed")

    def read(self, key: str) -> Optional[Stored]:
        try:
            obj = self._client().get_object(Bucket=self.bucket, Key=self._key(key))
            return Stored(obj["Body"].read(), obj["ETag"])
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
                raise PreconditionFailed() from exc
            raise self._unavailable("write", key, exc) from exc
        except BotoCoreError as exc:
            raise self._unavailable("write", key, exc) from exc


F = TypeVar("F", bound=FileStore)
S = TypeVar("S", bound=S3Store)


def store_from_uri(uri: str, *, file_store: type[F], s3_store: type[S], name: str) -> F | S:
    """Return the store for a ``s3://bucket/prefix`` or ``file://`` / plain path base.

    ``name`` labels the error for an unsupported scheme.
    """

    parsed = urlparse(uri)
    if parsed.scheme == "s3":
        return s3_store(bucket=parsed.netloc, prefix=parsed.path.strip("/"))
    # A Windows path such as D:\data\watchlists parses as scheme "d".
    if len(parsed.scheme) == 1:
        return file_store(root=Path(uri))
    if parsed.scheme in {"file", ""}:
        path = os.path.join(parsed.netloc, parsed.path.lstrip("/")) if parsed.netloc else parsed.path
        return file_store(root=Path(path))
    raise ValueError(f"Unsupported {name} storage scheme: {parsed.scheme}")


__all__ = [
    "ConditionalStore",
    "FileStore",
    "PreconditionFailed",
    "S3Store",
    "StoreUnavailable",
    "Stored",
    "store_from_uri",
]
