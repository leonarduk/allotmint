from __future__ import annotations

import os
from pathlib import Path


def safe_join(base: Path, *parts: str) -> Path:
    """Join *parts* onto *base*, raising ValueError on path traversal.

    Resolved path must remain inside *base*.  Use wherever user-supplied
    values are concatenated to a filesystem root.
    """
    resolved_base = os.path.realpath(base)
    candidate = os.path.realpath(os.path.join(base, *parts))
    if candidate != resolved_base and not candidate.startswith(resolved_base + os.sep):
        raise ValueError(f"Path traversal attempt blocked: {parts!r} escapes {base}")
    return Path(candidate)
