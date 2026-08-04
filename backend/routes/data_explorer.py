"""Read-only file explorer for the backend ``data/`` area.

Lets an admin browse the directory tree rooted at ``config.data_root`` and
preview small text files, for debugging what's actually on disk (cached
timeseries, account files, etc.) without shell access to the environment.
Never writes, deletes, or renames anything.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from backend.config import config
from backend.logging_setup import sanitise_log_value

router = APIRouter(prefix="/data-explorer", tags=["data-explorer"], dependencies=[Depends(get_current_user)])
logger = logging.getLogger("routes.data_explorer")

# Preview is capped well below typical request/response body limits so a
# multi-GB cache file can't be read into memory or hang the request.
MAX_PREVIEW_BYTES = 200_000

# Only a small allowlist of known-text extensions is ever previewed; anything
# else (parquet, binary caches, etc.) is rejected rather than streamed raw.
PREVIEWABLE_EXTENSIONS = {".json", ".csv", ".txt", ".log", ".yaml", ".yml", ".md"}


def _data_root() -> Path:
    root = config.data_root
    if root is None:
        raise HTTPException(status_code=501, detail="Data root is not configured")
    return root.resolve()


def _resolve_within_root(root: Path, rel_path: str) -> Path:
    """Resolve ``rel_path`` under ``root``, rejecting any attempt to escape it."""

    normalised = (rel_path or "").strip().replace("\\", "/")
    if normalised.startswith("/") or (len(normalised) > 1 and normalised[1] == ":"):
        raise HTTPException(status_code=400, detail="Invalid path")

    candidate = (root / normalised).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid path")
    return candidate


def _iso_mtime(stat_result: os.stat_result) -> str:
    return datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).isoformat()


@router.get("/tree")
async def list_directory(path: str = Query("")) -> dict[str, Any]:
    """List the immediate contents of a directory under the data root."""

    root = _data_root()
    if config.app_env == "aws":
        raise HTTPException(
            status_code=501,
            detail="Data explorer is only available against a local filesystem, not S3",
        )

    target = _resolve_within_root(root, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    entries: list[dict[str, Any]] = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        try:
            stat_result = child.stat()
        except OSError:
            logger.warning("Failed to stat %s", sanitise_log_value(child))
            continue
        entries.append(
            {
                "name": child.name,
                "path": child.relative_to(root).as_posix(),
                "type": "dir" if child.is_dir() else "file",
                "size": None if child.is_dir() else stat_result.st_size,
                "modified": _iso_mtime(stat_result),
            }
        )

    return {
        "path": "" if target == root else target.relative_to(root).as_posix(),
        "entries": entries,
    }


class FilePreviewResponse(BaseModel):
    """Response shape for GET /data-explorer/file."""

    path: str
    size: int
    modified: str
    truncated: bool = Field(
        description="True when the file exceeds MAX_PREVIEW_BYTES and content was cut off at that limit"
    )
    content: str


@router.get("/file", response_model=FilePreviewResponse)
async def read_file(path: str = Query(...)) -> dict[str, Any]:
    """Return a text preview of a single file under the data root."""

    root = _data_root()
    if config.app_env == "aws":
        raise HTTPException(
            status_code=501,
            detail="Data explorer is only available against a local filesystem, not S3",
        )

    target = _resolve_within_root(root, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if target.suffix.lower() not in PREVIEWABLE_EXTENSIONS:
        raise HTTPException(status_code=415, detail="File type is not previewable")

    stat_result = target.stat()
    try:
        with target.open("rb") as fh:
            raw = fh.read(MAX_PREVIEW_BYTES + 1)
    except OSError as exc:
        logger.warning("Failed to read %s: %s", sanitise_log_value(target), sanitise_log_value(exc))
        raise HTTPException(status_code=500, detail="Failed to read file") from exc

    truncated = len(raw) > MAX_PREVIEW_BYTES
    if truncated:
        raw = raw[:MAX_PREVIEW_BYTES]
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=415, detail="File is not valid UTF-8 text") from exc

    return {
        "path": target.relative_to(root).as_posix(),
        "size": stat_result.st_size,
        "modified": _iso_mtime(stat_result),
        "truncated": truncated,
        "content": content,
    }
