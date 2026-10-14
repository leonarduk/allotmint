"""Cheap change detection for files whose parsed contents are cached in-process.

A file's ``(mtime_ns, size)`` changes whenever it is rewritten, so a cache
keyed on it serves the parsed result until the file changes, at the cost of
one ``stat`` instead of an ``open`` + parse. Used by the admin listings that
scan every instrument / timeseries file on each request (#10754).
"""

from __future__ import annotations

import os
from pathlib import Path

FileSignature = tuple[int, int] | None


def file_signature(path: str | os.PathLike[str] | Path) -> FileSignature:
    """``(mtime_ns, size)`` of ``path``, or ``None`` when it cannot be stat-ed (e.g. absent)."""
    try:
        stat = os.stat(path)
    except (OSError, ValueError):
        return None
    return stat.st_mtime_ns, stat.st_size
