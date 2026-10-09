"""Where digest records live: beside the bot registry's documents (#10485).

The base is ``BOTS_DIGESTS_URI`` when set, otherwise ``<BOTS_STORAGE_URI>/digests``
(the registry's base, :func:`backend.bots.store.storage_base`; deployed that is
``s3://<bucket>/bots``). Each record is one JSON object under it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

from backend.bots.store import storage_base
from backend.common.storage import FileJSONStorage, JSONStorage, S3JSONStorage

# Path segments (owner ids, dates) are restricted so a caller-supplied value
# can never escape the configured location.
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FILE_SCHEME = "file://"


def safe_segment(value: str) -> str:
    """Return ``value`` when it is a safe single path segment, else raise ``ValueError``."""

    if not isinstance(value, str) or not _SAFE_SEGMENT.match(value) or ".." in value:
        raise ValueError("unsafe path segment")
    return value


def location(env_var: str, subdir: str) -> str:
    """``env_var`` when set, else ``<registry storage base>/<subdir>``; ``file://`` is dropped."""

    base = os.getenv(env_var, "").strip() or f"{storage_base()}/{subdir}"
    if base.startswith(_FILE_SCHEME):
        base = base[len(_FILE_SCHEME) :]
    return base.rstrip("/\\")


def json_storage(base: str, *segments: str) -> JSONStorage:
    """Return storage for ``<base>/<segments...>``; every segment must be safe."""

    parts = [safe_segment(segment) for segment in segments]
    if base.startswith("s3://"):
        parsed = urlparse(base)
        key = "/".join([p for p in [parsed.path.strip("/")] if p] + parts)
        return S3JSONStorage(bucket=parsed.netloc, key=key)
    return FileJSONStorage(Path(base).joinpath(*parts))
