"""Where bot records live: a local directory, or an S3 prefix in deployment.

Follows ``backend/data_steward/store.py`` (#10471): a location is taken from
an env var when set (e.g. ``s3://<bucket>/bots/digests``), otherwise a
directory under ``{data_root}``. Each record is one JSON object.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

from backend.common.storage import FileJSONStorage, JSONStorage, S3JSONStorage
from backend.config import config

# Path segments (owner ids, bot ids, dates) are restricted so a caller-supplied
# value can never escape the configured location.
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def safe_segment(value: str) -> str:
    """Return ``value`` when it is a safe single path segment, else raise ``ValueError``."""

    if not isinstance(value, str) or not _SAFE_SEGMENT.match(value) or ".." in value:
        raise ValueError("unsafe path segment")
    return value


def location(env_var: str, default_subdir: str) -> str:
    """Return the configured base location for ``env_var``, or ``{data_root}/<default_subdir>``."""

    configured = os.getenv(env_var, "").strip()
    if configured:
        return configured.rstrip("/")
    data_root = getattr(config, "data_root", None)
    base = Path(data_root) if data_root else Path(__file__).resolve().parents[2] / "data"
    return str(base / default_subdir)


def json_storage(base: str, *segments: str) -> JSONStorage:
    """Return storage for ``<base>/<segments...>``; every segment must be safe."""

    parts = [safe_segment(segment) for segment in segments]
    if base.startswith("s3://"):
        parsed = urlparse(base)
        key = "/".join([p for p in [parsed.path.strip("/")] if p] + parts)
        return S3JSONStorage(bucket=parsed.netloc, key=key)
    return FileJSONStorage(Path(base).joinpath(*parts))
