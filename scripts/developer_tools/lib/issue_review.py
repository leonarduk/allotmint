"""Shared helpers for parsing LLM issue-review responses.

Used by both b_create_issue.py (drafting a new issue) and n_review_issue.py
(refreshing an existing one), which send differently-worded prompts to the
model but expect the same TITLE:/BODY: response format back.
"""

from __future__ import annotations

import re


def parse_review_response(
    response: str, fallback_title: str, fallback_body: str
) -> tuple[str, str]:
    """Parse the model's TITLE/BODY response, falling back to the originals on any mismatch."""
    match = re.search(r"TITLE:\s*(.*?)\s*\nBODY:\s*\n?(.*)", response, re.DOTALL)
    if not match:
        return fallback_title, fallback_body
    title = match.group(1).strip()
    body = match.group(2).strip()
    if not title or not body:
        return fallback_title, fallback_body
    return title, body
