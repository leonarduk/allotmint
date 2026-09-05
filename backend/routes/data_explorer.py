"""Read-only file explorer for the backend data area.

Lets an admin browse the directory tree rooted at ``config.data_root`` (local
filesystem) or under ``DATA_BUCKET`` (S3, when ``config.app_env == "aws"``)
and preview small text files, for debugging what's actually on disk/in S3
(cached timeseries, account files, etc.) without shell access to the
environment. Never writes, deletes, or renames anything.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from backend.common.data_providers import DATA_BUCKET_ENV
from backend.config import config
from backend.logging_setup import sanitise_log_value

router = APIRouter(prefix="/data-explorer", tags=["data-explorer"], dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)

# Preview is capped well below typical request/response body limits so a
# multi-GB cache file can't be read into memory or hang the request.
MAX_PREVIEW_BYTES = 200_000

# Only a small allowlist of known-text extensions is ever previewed; anything
# else (parquet, binary caches, etc.) is rejected rather than streamed raw.
PREVIEWABLE_EXTENSIONS = {".json", ".csv", ".txt", ".log", ".yaml", ".yml", ".md"}

# Friendly message shown to the user in place of the (technically accurate but
# unhelpful-looking) 415 for a file type that isn't in PREVIEWABLE_EXTENSIONS,
# e.g. clicking a binary VCS object like `.git/index` (umbrella issue #6109;
# local-explorer follow-up #6112).
NOT_PREVIEWABLE_DETAIL = "This file type can't be previewed here (binary or unsupported format)."

# VCS/IDE housekeeping folders that belong to the tooling around the data
# repo, not the data itself. Excluded from the local tree listing so they
# don't clutter (or get clicked into) alongside real data folders. Kept as a
# narrow, named set rather than "skip anything starting with a dot" since
# legitimate dotfiles/dotfolders could exist in the data repo.
EXCLUDED_LOCAL_DIR_NAMES = {".git", ".idea"}


def _reject_unsafe_relative_path(rel_path: str) -> str:
    """Normalise ``rel_path`` to a clean, root-relative path, or reject it.

    Shared by both the local-filesystem and S3 branches: rejects absolute
    paths, Windows drive prefixes, and any ``..`` segment before the path is
    ever joined onto a root/prefix.
    """

    normalised = (rel_path or "").strip().replace("\\", "/")
    if normalised.startswith("/") or (len(normalised) > 1 and normalised[1] == ":"):
        raise HTTPException(status_code=400, detail="Invalid path")

    segments = [seg for seg in normalised.split("/") if seg not in ("", ".")]
    if any(seg == ".." for seg in segments):
        raise HTTPException(status_code=400, detail="Invalid path")
    return "/".join(segments)


def _data_root() -> Path:
    root = config.data_root
    if root is None:
        raise HTTPException(status_code=501, detail="Data root is not configured")
    return root.resolve()


def _resolve_within_root(root: Path, rel_path: str) -> Path:
    """Resolve ``rel_path`` under ``root``, rejecting any attempt to escape it."""

    normalised = _reject_unsafe_relative_path(rel_path)
    candidate = (root / normalised).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid path")
    return candidate


def _s3_bucket() -> str:
    bucket = os.getenv(DATA_BUCKET_ENV)
    if not bucket:
        raise HTTPException(status_code=501, detail=f"{DATA_BUCKET_ENV} is not configured")
    return bucket


def _s3_client() -> Any:
    import boto3  # type: ignore

    return boto3.client("s3")


def _list_directory_s3(rel_path: str) -> dict[str, Any]:
    bucket = _s3_bucket()
    prefix = _reject_unsafe_relative_path(rel_path)
    prefix = f"{prefix}/" if prefix else ""

    client = _s3_client()
    entries: list[dict[str, Any]] = []
    seen_dirs: set[str] = set()
    found_any = False
    token: str | None = None
    while True:
        params: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix, "Delimiter": "/"}
        if token:
            params["ContinuationToken"] = token
        try:
            resp = client.list_objects_v2(**params)
        except (ClientError, BotoCoreError) as exc:
            logger.warning(
                "S3 list failed for s3://%s/%s: %s",
                sanitise_log_value(bucket),
                sanitise_log_value(prefix),
                sanitise_log_value(exc),
            )
            raise HTTPException(status_code=502, detail="Failed to list S3 data") from exc

        for common in resp.get("CommonPrefixes", []):
            key = common.get("Prefix", "")
            name = key[len(prefix) :].rstrip("/")
            if not name or name in seen_dirs:
                continue
            seen_dirs.add(name)
            found_any = True
            entries.append(
                {
                    "name": name,
                    "path": key.rstrip("/"),
                    "type": "dir",
                    "size": None,
                    "modified": None,
                }
            )

        for obj in resp.get("Contents", []):
            key = obj.get("Key", "")
            name = key[len(prefix) :]
            if not name or "/" in name:
                continue
            found_any = True
            last_modified = obj.get("LastModified")
            entries.append(
                {
                    "name": name,
                    "path": key,
                    "type": "file",
                    "size": obj.get("Size"),
                    "modified": (last_modified.astimezone(timezone.utc).isoformat() if last_modified else None),
                }
            )

        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break

    if not found_any and prefix:
        raise HTTPException(status_code=404, detail="Path not found")

    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
    return {"path": prefix.rstrip("/"), "entries": entries}


def _read_file_s3(rel_path: str) -> dict[str, Any]:
    bucket = _s3_bucket()
    key = _reject_unsafe_relative_path(rel_path)
    if not key:
        raise HTTPException(status_code=400, detail="Invalid path")
    if Path(key).suffix.lower() not in PREVIEWABLE_EXTENSIONS:
        raise HTTPException(status_code=415, detail=NOT_PREVIEWABLE_DETAIL)

    client = _s3_client()
    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"404", "NoSuchKey", "NotFound"}:
            raise HTTPException(status_code=404, detail="File not found") from exc
        logger.warning(
            "S3 head failed for s3://%s/%s: %s",
            sanitise_log_value(bucket),
            sanitise_log_value(key),
            sanitise_log_value(exc),
        )
        raise HTTPException(status_code=502, detail="Failed to read file from S3") from exc
    except BotoCoreError as exc:
        logger.warning(
            "S3 head failed for s3://%s/%s: %s",
            sanitise_log_value(bucket),
            sanitise_log_value(key),
            sanitise_log_value(exc),
        )
        raise HTTPException(status_code=502, detail="Failed to read file from S3") from exc

    size = head["ContentLength"]
    truncated = size > MAX_PREVIEW_BYTES
    get_kwargs: dict[str, Any] = {"Bucket": bucket, "Key": key}
    if truncated:
        get_kwargs["Range"] = f"bytes=0-{MAX_PREVIEW_BYTES - 1}"
    try:
        obj = client.get_object(**get_kwargs)
        raw = obj["Body"].read()
    except (ClientError, BotoCoreError) as exc:
        logger.warning(
            "S3 read failed for s3://%s/%s: %s",
            sanitise_log_value(bucket),
            sanitise_log_value(key),
            sanitise_log_value(exc),
        )
        raise HTTPException(status_code=502, detail="Failed to read file from S3") from exc

    try:
        content = raw.decode(encoding="utf-8", errors="replace")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=415, detail="File is not valid UTF-8 text") from exc

    modified = head.get("LastModified")
    return {
        "path": key,
        "size": size,
        "modified": modified.astimezone(timezone.utc).isoformat() if modified else None,
        "truncated": truncated,
        "content": content,
    }


def _iso_mtime(stat_result: os.stat_result) -> str:
    return datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).isoformat()


@router.get("/tree")
def list_directory(path: str = Query("")) -> dict[str, Any]:
    """List the immediate contents of a directory under the data root."""

    if config.app_env == "aws":
        return _list_directory_s3(path)

    root = _data_root()
    target = _resolve_within_root(root, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    entries: list[dict[str, Any]] = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if child.is_dir() and child.name in EXCLUDED_LOCAL_DIR_NAMES:
            continue
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
def read_file(path: str = Query(...)) -> dict[str, Any]:
    """Return a text preview of a single file under the data root."""

    if config.app_env == "aws":
        return _read_file_s3(path)

    root = _data_root()
    target = _resolve_within_root(root, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if target.suffix.lower() not in PREVIEWABLE_EXTENSIONS:
        raise HTTPException(status_code=415, detail=NOT_PREVIEWABLE_DETAIL)

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
        content = raw.decode(encoding="utf-8", errors="replace")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=415, detail="File is not valid UTF-8 text") from exc

    return {
        "path": target.relative_to(root).as_posix(),
        "size": stat_result.st_size,
        "modified": _iso_mtime(stat_result),
        "truncated": truncated,
        "content": content,
    }
