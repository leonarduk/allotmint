from __future__ import annotations

import os
import re
from pathlib import Path

_LOG_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def safe_join(base: Path, *parts: str) -> Path:
    """Join *parts* onto *base*, raising ValueError on path traversal.

    The resolved path must be a *strict descendant* of *base*.  Parts that
    resolve to the base itself (empty string, ".") are also rejected because
    callers always expect a named child, not the root directory.
    """
    resolved_base = os.path.realpath(base)
    candidate = os.path.realpath(os.path.join(base, *parts))
    if not candidate.startswith(resolved_base + os.sep):
        raise ValueError(f"Path traversal attempt blocked: {parts!r} escapes {base}")
    return Path(candidate)


def sanitize_for_log(value: object) -> str:
    """Return a string safe for plain-text logs (strips control characters)."""
    return _LOG_CTRL_RE.sub("", str(value))
