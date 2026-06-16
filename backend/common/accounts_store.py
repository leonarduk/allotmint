"""Pluggable persistence for writable account documents.

Local development persists account JSON files under an on-disk accounts root,
mutating them in place with file locking.  The deployed AWS environment has no
writable, non-global on-disk root: ``configure_runtime_paths`` always falls
back to the read-only shared/global demo dataset baked into the Lambda image,
so every write tripped the ``accounts_root_is_global`` guard and returned
``HTTP 400`` (issue #4275).

This module abstracts the read/modify/write of a single account *document*
(a holdings file or a transactions file) so write handlers can persist manual
holdings and transactions to a writable store that is **separate** from the
read-only ``accounts/`` demo data:

* :class:`LocalAccountsStore` keeps the existing on-disk, file-locked behaviour
  used by local development and the test suite.
* :class:`S3AccountsStore` writes each document directly to a dedicated S3
  prefix (``writable-accounts/`` by default) that never overlaps the shared
  ``accounts/`` demo dataset, satisfying the "never mutate the shared dataset"
  constraint while still persisting across the ephemeral Lambda filesystem.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import platform
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from backend.common.path_utils import safe_join

try:  # Unix-like systems
    import fcntl  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]
    if platform.system() == "Windows":
        import msvcrt  # type: ignore
    else:  # pragma: no cover - unsupported platform
        raise
else:  # pragma: no cover - Unix
    msvcrt = None  # type: ignore[assignment]

logger = logging.getLogger("accounts_store")

# Prefix (relative to the data bucket) under which per-owner writable account
# documents live.  Kept distinct from the read-only ``accounts/`` demo prefix
# so writes can never mutate the shared dataset.
WRITABLE_ACCOUNTS_PREFIX = (os.getenv("WRITABLE_ACCOUNTS_PREFIX") or "writable-accounts").strip("/")


def _lock_file(f) -> None:
    """Lock ``f`` for exclusive access."""
    if fcntl:
        fcntl.flock(f, fcntl.LOCK_EX)  # type: ignore[attr-defined]
    else:  # pragma: no cover - Windows
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 0x7FFFFFFF)  # type: ignore[attr-defined]


def _unlock_file(f) -> None:
    """Unlock ``f``."""
    if fcntl:
        fcntl.flock(f, fcntl.LOCK_UN)  # type: ignore[attr-defined]
    else:  # pragma: no cover - Windows
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 0x7FFFFFFF)  # type: ignore[attr-defined]


def _coerce_document(loaded: Any, default: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``loaded`` if it is a dict, otherwise a fresh copy of ``default``."""
    if isinstance(loaded, dict):
        return loaded
    return copy.deepcopy(default)


def _default_person_payload(owner: str) -> Dict[str, Any]:
    return {
        "dob": "",
        "email": "",
        "full_name": "",
        "owner": owner,
        "holdings": [],
        "viewers": [],
    }


@dataclass
class LocalAccountsStore:
    """On-disk, file-locked account document store (local dev / tests).

    ``is_global`` marks the resolved root as the read-only shared demo dataset;
    write handlers refuse to mutate it.  ``local_root`` exposes the directory so
    callers can still drive path-based helpers (e.g. portfolio rebuild).
    """

    root: Optional[Path]
    is_global: bool = False

    @property
    def local_root(self) -> Optional[Path]:
        return self.root

    def _owner_dir(self, owner: str, *, create: bool) -> Path:
        if self.root is None:
            raise FileNotFoundError("accounts root not configured")
        owner_dir = safe_join(self.root, owner)
        if create:
            owner_dir.mkdir(parents=True, exist_ok=True)
        return owner_dir

    @contextmanager
    def edit_document(
        self,
        owner: str,
        filename: str,
        *,
        default: Dict[str, Any],
        trailing_newline: bool = False,
    ) -> Iterator[Dict[str, Any]]:
        owner_dir = self._owner_dir(owner, create=True)
        file_path = safe_join(owner_dir, filename)
        file_existed = file_path.exists()
        mode = "r+" if file_existed else "w+"
        committed = False
        pending_error: BaseException | None = None
        pending_traceback = None
        with file_path.open(mode, encoding="utf-8") as f:
            _lock_file(f)
            try:
                f.seek(0)
                try:
                    loaded = json.load(f)
                except (json.JSONDecodeError, OSError):
                    loaded = None
                data = _coerce_document(loaded, default)
                try:
                    yield data
                except BaseException as exc:  # noqa: BLE001 - re-raised below
                    pending_error = exc
                    pending_traceback = exc.__traceback__
                else:
                    f.seek(0)
                    f.truncate()
                    json.dump(data, f, indent=2)
                    if trailing_newline:
                        f.write("\n")
                    f.flush()
                    os.fsync(f.fileno())
                    committed = True
            finally:
                _unlock_file(f)

        if not committed and not file_existed:
            with suppress(FileNotFoundError):
                file_path.unlink()
        if pending_error is not None:
            raise pending_error.with_traceback(pending_traceback)

    def read_document(self, owner: str, filename: str) -> Optional[Dict[str, Any]]:
        try:
            owner_dir = self._owner_dir(owner, create=False)
            file_path = safe_join(owner_dir, filename)
        except (FileNotFoundError, ValueError):
            return None
        if not file_path.exists():
            return None
        try:
            loaded = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return loaded if isinstance(loaded, dict) else None

    def list_owner_files(self, owner: str) -> List[str]:
        try:
            owner_dir = self._owner_dir(owner, create=False)
        except (FileNotFoundError, ValueError):
            return []
        if not owner_dir.exists():
            return []
        return sorted(p.name for p in owner_dir.glob("*.json") if p.is_file())

    def owner_exists(self, owner: str) -> bool:
        try:
            owner_dir = self._owner_dir(owner, create=False)
        except (FileNotFoundError, ValueError):
            return False
        return owner_dir.exists()

    def iter_transaction_documents(self) -> Iterator[Tuple[str, str, Dict[str, Any]]]:
        if self.root is None or not self.root.exists():
            return
        for path in self.root.glob("*/*_transactions.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            owner = str(data.get("owner") or path.parent.name)
            account_raw = str(data.get("account_type") or path.stem.replace("_transactions", ""))
            yield owner, account_raw, data

    def ensure_owner(self, owner: str) -> None:
        """Implicit account-creation path for the local/file-backed store.

        Scaffolds a minimal owner directory (person.json with holdings and
        viewers keys) the first time a write endpoint is called for an owner
        that does not yet exist.  This is **not** the only creation path: when
        an admin approves a signup request,
        :func:`backend.common.compliance.ensure_owner_scaffold` is used
        instead, which also records the owner's email so that
        :func:`backend.auth._allowed_emails` admits them at login — before any
        write is made.  Do not call directly unless you understand the full
        account-creation lifecycle.
        """
        if self.is_global or self.root is None:
            return
        if self.read_document(owner, "person.json") is not None:
            return
        with self.edit_document(owner, "person.json", default=_default_person_payload(owner)) as data:
            data.setdefault("owner", owner)
            data.setdefault("holdings", [])
            data.setdefault("viewers", [])


@dataclass
class S3AccountsStore:
    """Direct-to-S3 account document store for the deployed AWS environment.

    Each document is a single S3 object under ``{prefix}/{owner}/{filename}``.
    Writes read the current object fresh before mutating, so concurrent Lambda
    instances never persist stale local state.  The prefix is deliberately
    distinct from the read-only ``accounts/`` demo prefix.
    """

    bucket: str
    prefix: str = WRITABLE_ACCOUNTS_PREFIX
    client: Any | None = None
    is_global: bool = False
    local_root: Optional[Path] = field(default=None)

    def _s3(self):
        if self.client is None:
            import boto3  # type: ignore

            self.client = boto3.client("s3")
        return self.client

    def _key(self, owner: str, filename: str) -> str:
        return f"{self.prefix}/{owner}/{filename}"

    def read_document(self, owner: str, filename: str) -> Optional[Dict[str, Any]]:
        from botocore.exceptions import BotoCoreError, ClientError

        key = self._key(owner, filename)
        try:
            obj = self._s3().get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"NoSuchKey", "404", "NotFound"}:
                return None
            logger.warning("S3 read failed for s3://%s/%s: %s", self.bucket, key, exc)
            return None
        except BotoCoreError as exc:
            logger.warning("S3 read failed for s3://%s/%s: %s", self.bucket, key, exc)
            return None
        body = obj.get("Body")
        text = body.read().decode("utf-8-sig").strip() if body else ""
        if not text:
            return None
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            return None
        return loaded if isinstance(loaded, dict) else None

    def _put_document(self, owner: str, filename: str, data: Dict[str, Any]) -> None:
        key = self._key(owner, filename)
        body = json.dumps(data, indent=2).encode("utf-8")
        self._s3().put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )

    @contextmanager
    def edit_document(
        self,
        owner: str,
        filename: str,
        *,
        default: Dict[str, Any],
        trailing_newline: bool = False,
    ) -> Iterator[Dict[str, Any]]:
        # ``trailing_newline`` is accepted for signature parity with the local
        # store; S3 objects are stored without a trailing newline.
        del trailing_newline
        existing = self.read_document(owner, filename)
        data = _coerce_document(existing if existing is not None else None, default)
        yield data
        self._put_document(owner, filename, data)

    def list_owner_files(self, owner: str) -> List[str]:
        prefix = f"{self.prefix}/{owner}/"
        names: List[str] = []
        for key in self._iter_keys(prefix):
            name = key[len(prefix) :]
            if name and "/" not in name:
                names.append(name)
        return sorted(names)

    def owner_exists(self, owner: str) -> bool:
        prefix = f"{self.prefix}/{owner}/"
        return any(True for _ in self._iter_keys(prefix, limit=1))

    def iter_transaction_documents(self) -> Iterator[Tuple[str, str, Dict[str, Any]]]:
        prefix = f"{self.prefix}/"
        for key in self._iter_keys(prefix):
            name = key[len(prefix) :]
            parts = name.split("/")
            if len(parts) != 2 or not parts[1].endswith("_transactions.json"):
                continue
            owner = parts[0]
            data = self.read_document(owner, parts[1])
            if not isinstance(data, dict):
                continue
            account_raw = str(data.get("account_type") or parts[1].replace("_transactions.json", ""))
            yield str(data.get("owner") or owner), account_raw, data

    def ensure_owner(self, owner: str) -> None:
        """Implicit account-creation path for the S3-backed store.

        Scaffolds a minimal owner directory (person.json with holdings and
        viewers keys) the first time a write endpoint is called for an owner
        that does not yet exist.  This is **not** the only creation path: when
        an admin approves a signup request,
        :func:`backend.common.compliance.ensure_owner_scaffold` is used
        instead, which also records the owner's email so that
        :func:`backend.auth._allowed_emails` admits them at login — before any
        write is made.  Do not call directly unless you understand the full
        account-creation lifecycle.
        """
        if self.read_document(owner, "person.json") is not None:
            return
        with self.edit_document(owner, "person.json", default=_default_person_payload(owner)) as data:
            data.setdefault("owner", owner)
            data.setdefault("holdings", [])
            data.setdefault("viewers", [])

    def _iter_keys(self, prefix: str, *, limit: Optional[int] = None) -> Iterator[str]:
        from botocore.exceptions import BotoCoreError, ClientError

        client = self._s3()
        token: Optional[str] = None
        seen = 0
        while True:
            kwargs: Dict[str, Any] = {"Bucket": self.bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            try:
                resp = client.list_objects_v2(**kwargs)
            except (ClientError, BotoCoreError) as exc:
                logger.warning("S3 list failed for s3://%s/%s: %s", self.bucket, prefix, exc)
                return
            for entry in resp.get("Contents", []) or []:
                key = entry.get("Key")
                if not key:
                    continue
                yield key
                seen += 1
                if limit is not None and seen >= limit:
                    return
            if not resp.get("IsTruncated"):
                return
            token = resp.get("NextContinuationToken")
            if not token:
                return


__all__ = [
    "WRITABLE_ACCOUNTS_PREFIX",
    "LocalAccountsStore",
    "S3AccountsStore",
]
