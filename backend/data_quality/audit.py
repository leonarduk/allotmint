"""Append-only audit trail for data-quality fix actions.

Records every applied fix (before/after snapshots, actor, timestamp) as one
JSON object per line in a JSONL file, so the history is durable and replayable.
Each entry is written with a single ``O_APPEND`` ``write()`` (atomic on
POSIX) and fsync'd before returning; the file is created if missing.

The audit file lives under ``config.audit_dir`` when configured, otherwise
``{config.data_root}/audit`` — the same data root that holds accounts/cache.
Tests override ``config.audit_dir`` (or monkeypatch :func:`audit_path`) to keep
writes out of the repo.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.config import config

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX (e.g. Windows) platform
    fcntl = None  # type: ignore[assignment]

_AUDIT_FILENAME = "data_quality_audit.jsonl"
_lock = threading.Lock()


def audit_path() -> Path:
    """Return the audit JSONL path for the current config."""
    configured = getattr(config, "audit_dir", None)
    if configured:
        return Path(configured) / _AUDIT_FILENAME
    data_root = getattr(config, "data_root", None)
    base = Path(data_root) if data_root else Path(__file__).resolve().parents[2] / "data"
    return base / "audit" / _AUDIT_FILENAME


def _atomic_append_text(path: Path, line: str) -> None:
    """Append ``line`` to ``path`` with a single atomic write.

    The file is opened with ``O_APPEND`` and the entry (plus any separator
    newline) is written in one ``write()`` call, so POSIX guarantees it lands
    at the current end of file without interleaving — concurrent writers
    (e.g. parallel Lambda invocations) cannot clobber each other's entries.
    The write is fsync'd before returning so a crash cannot lose it.

    The trailing-newline check and the write are serialised with an advisory
    ``flock`` (and the module threading lock) so the separator decision
    cannot go stale between the check and the write; without a lock two
    writers could both decide a separator is needed and corrupt the JSONL
    with a spurious blank line.  The file is created if missing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        _acquire_append_lock(fd)
        separator = b""
        try:
            if os.fstat(fd).st_size > 0:
                with open(path, "rb") as existing:
                    existing.seek(-1, os.SEEK_END)
                    if existing.read(1) != b"\n":
                        # Ensure the previous entry is separated from this one
                        # even when the file lacks a trailing newline
                        # (crash/partial write recovery).
                        separator = b"\n"
        except OSError:
            separator = b""
        payload = line if line.endswith("\n") else line + "\n"
        # One write: separator + payload, so O_APPEND atomicity covers the
        # whole entry rather than two separately-writable pieces.
        os.write(fd, separator + payload.encode("utf-8"))
        os.fsync(fd)
    finally:
        _release_append_lock(fd)
        os.close(fd)


def _acquire_append_lock(fd: int) -> None:
    """Serialise the separator-check + write across processes (POSIX)."""
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_EX)  # type: ignore[attr-defined]


def _release_append_lock(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[attr-defined]


def append_audit(
    *,
    action: str,
    issue_id: str,
    entity: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    actor: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Record one audit entry and return it. Reversible actions pass the
    ``before`` snapshot so ``undo`` can restore it."""
    entry: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "issue_id": issue_id,
        "entity": entity,
        "before": before,
        "after": after,
        "actor": actor,
    }
    if extra:
        entry["extra"] = extra
    with _lock:
        _atomic_append_text(audit_path(), json.dumps(entry) + "\n")
    return entry


def read_audit(limit: Optional[int] = None) -> list[dict[str, Any]]:
    """Return audit entries, newest first. Missing/corrupt file -> []."""
    path = audit_path()
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    if limit is not None:
        return entries[:limit]
    return entries


def find_audit_entry(entry_id: str) -> Optional[dict[str, Any]]:
    for entry in read_audit():
        if entry.get("id") == entry_id:
            return entry
    return None
