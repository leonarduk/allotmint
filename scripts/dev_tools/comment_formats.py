"""Format PR comments for output."""

from __future__ import annotations

import json
from typing import Any, Iterable


def to_jsonl(comments: list[dict[str, Any]]) -> Iterable[str]:
    """Yield JSONL lines (one JSON object per line)."""
    for comment in comments:
        yield json.dumps(comment)


def to_fixer(comments: list[dict[str, Any]]) -> Iterable[str]:
    """Yield compact fixer format: path:line — body or (general) — body."""
    for comment in comments:
        comment_type = comment.get("type")

        if comment_type == "inline":
            path = comment.get("path")
            line = comment.get("line")
            body = comment.get("body", "").strip()
            if path and line:
                yield f"{path}:{line} — {body}"
        elif comment_type == "top-level":
            body = comment.get("body", "").strip()
            yield f"(general) — {body}"
