from __future__ import annotations

from pathlib import Path


def safe_join(base: Path, *parts: str) -> Path:
    """Join *parts* onto *base*, raising ValueError on path traversal.

    Resolved path must remain inside *base*.  *base* is resolved with
    strict=False so that scaffold creation for new owners (where the
    directory does not yet exist) does not produce a spurious error.
    Use wherever user-supplied values are concatenated to a filesystem root.
    """
    resolved_base = Path(base).resolve()
    candidate = Path(base).joinpath(*parts).resolve()
    if candidate != resolved_base and not candidate.is_relative_to(resolved_base):
        raise ValueError(f"Path traversal attempt blocked: {parts!r} escapes {base}")
    return candidate
