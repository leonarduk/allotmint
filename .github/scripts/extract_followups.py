"""Extract follow-up issue titles from section 5 of an AI review."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def extract_followups(review_text: str) -> list[str]:
    """Return follow-up issue titles from section 5 of the review.

    Looks for a heading matching '5. Suggested follow-up issues' and extracts
    bullet items (- or *) until the next heading or the verdict line.
    """
    section_match = re.search(r'^#{1,6}\s+5\.\s+\S', review_text, re.MULTILINE)
    if not section_match:
        return []

    section_start = section_match.end()
    next_heading = re.search(r'^#{1,6}\s+\S', review_text[section_start:], re.MULTILINE)
    if next_heading and next_heading.start() > 0:
        section_text = review_text[section_start : section_start + next_heading.start()]
    else:
        section_text = review_text[section_start:]

    # Stop before the verdict line in case it falls inside the section
    verdict_match = re.search(r'^\*\*(APPROVE|REQUEST CHANGES)\*\*', section_text, re.MULTILINE)
    if verdict_match:
        section_text = section_text[: verdict_match.start()]

    verdict_title_re = re.compile(r'^\*\*(APPROVE|REQUEST CHANGES)\*\*', re.IGNORECASE)
    titles = []
    for m in re.finditer(r'^[-*]\s+(.+)', section_text, re.MULTILINE):
        title = m.group(1).strip()
        if title and not verdict_title_re.match(title):
            titles.append(title)
    return titles


def main(review_file: str) -> int:
    """Read review file, extract follow-up titles, print as JSON array."""
    try:
        review_text = Path(review_file).read_text()
    except FileNotFoundError:
        print(f"ERROR: Review file not found: {review_file}", file=sys.stderr)
        return 1

    titles = extract_followups(review_text)
    print(json.dumps(titles))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <review_file>", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1]))
