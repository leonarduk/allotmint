"""Append-only audit trail for data-quality fix actions.

Records every applied fix (before/after snapshots, actor, timestamp) as one
JSON object per line in a JSONL file, so the history is durable and replayable.
Writes are atomic (temp file + rename) and the file is created if missing.

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
    """Append ``line`` to ``path`` via a temp file + rename.

    Reads the existing file (if any), writes the combined content to a
    ``.tmp`` sibling, fsyncs it, then renames over the original — so a failed
    write or crash cannot leave the trail partially written or corrupted.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        fh.write(existing)
        fh.write(line)
        if existing and not existing.endswith("\n"):
            fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


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
