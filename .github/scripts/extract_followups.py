"""Extract follow-up issue titles from an AI review's section 5.

Reads the review markdown file passed as the first argument and prints a
JSON array of follow-up issue title strings to stdout.  Exits 0 whether
or not any titles are found — an empty array ``[]`` is a valid result.

Usage::

    python3 extract_followups.py /tmp/claude_review_body.md

Section 5 is identified by a heading that matches::

    ### 5. Suggested follow-up issues

Each bullet item under that heading (lines starting with ``-`` or ``*``)
is treated as one follow-up title.  Inline code backticks and leading/
trailing whitespace are stripped.  Parsing stops at the next ``###``
heading or the end of file.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


_SECTION_HEADING = re.compile(r"^###\s+5[.\s]", re.IGNORECASE)
_NEXT_HEADING = re.compile(r"^###")
_BULLET = re.compile(r"^[-*]\s+")


def extract_followups(review_text: str) -> list[str]:
    """Return follow-up titles from section 5 of *review_text*."""
    lines = review_text.splitlines()
    in_section = False
    titles: list[str] = []

    for line in lines:
        if _SECTION_HEADING.match(line):
            in_section = True
            continue

        if in_section:
            if _NEXT_HEADING.match(line):
                break
            if _BULLET.match(line):
                # Strip leading bullet marker, surrounding backticks, and whitespace.
                raw = _BULLET.sub("", line).strip()
                raw = raw.strip("`").strip()
                if raw:
                    titles.append(raw)

    return titles


def main(review_file: str) -> int:
    try:
        text = Path(review_file).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"ERROR: file not found: {review_file}", file=sys.stderr)
        return 1

    titles = extract_followups(text)
    print(json.dumps(titles))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <review_file>", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1]))
