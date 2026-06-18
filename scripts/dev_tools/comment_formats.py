"""Format PR comments for output."""

from __future__ import annotations

import json
from typing import Any, Iterable


def to_jsonl(comments: list[dict[str, Any]]) -> Iterable[str]:
    """Yield JSONL lines (one JSON object per line)."""
    for comment in comments:
        yield json.dumps(comment)


def to_fixer(comments: list[dict[str, Any]]) -> Iterable[str]:
    """Yield compact fixer format: path:line — body or (general) — body.

    Multi-line bodies are indented for readability. Inline comments missing
    path/line fall back to (general) format. Unknown comment types also use
    (general) format with type label for debugging.
    """
    for comment in comments:
        comment_type = comment.get("type")
        body = comment.get("body", "")
        lines = body.split("\n")
        prefix = ""

        if comment_type == "inline":
            path = comment.get("path")
            line = comment.get("line")
            if path and line:
                prefix = f"{path}:{line} — "
            else:
                prefix = "(general) — "
        elif comment_type == "top-level":
            prefix = "(general) — "
        else:
            prefix = f"({comment_type}) — "

        if lines:
            yield f"{prefix}{lines[0]}"
            for line in lines[1:]:
                yield f"  {line}"
