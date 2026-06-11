"""Extract follow-up issue titles from section 5 of an AI review."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Require at least 3 chars so trivial backtick tokens (`` `s` ``, `` `1` ``)
# don't masquerade as a file/function/identifier reference.
_REFERENCE_PATTERN = re.compile(r'`[^`]{3,}`')

# Generic, low-value phrasing that gives an agent nothing concrete to act on.
# A title is only rejected if it matches one of these AND has no backtick-quoted
# file/function/identifier reference (see _is_low_specificity).
_GENERIC_PHRASING_PATTERNS = [
    re.compile(
        r'\bconsider adding (?:more )?(?:detailed|descriptive)?\s*'
        r'(?:comments?|logging|documentation|tests?)\b.*\bfor clarity\b',
        re.IGNORECASE,
    ),
    re.compile(r'\bimprove readability\b', re.IGNORECASE),
    re.compile(r'\badd(?:ing)? more context\b', re.IGNORECASE),
]


def _is_low_specificity(title: str) -> bool:
    """Return True if the title is too generic to act on without a reference."""
    if _REFERENCE_PATTERN.search(title):
        return False
    return any(pattern.search(title) for pattern in _GENERIC_PHRASING_PATTERNS)


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
        if not title or verdict_title_re.match(title):
            continue
        if _is_low_specificity(title):
            print(f"Skipping low-specificity follow-up: {title}", file=sys.stderr)
            continue
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
