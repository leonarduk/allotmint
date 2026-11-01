"""Keep only the AI review's real-gap follow-ups before they are filed as issues.

``_ai-pr-review.yml`` files every bullet under a review's "Suggested follow-up
issues" section as an ``ai-suggested`` issue. Most of those were nits (add a
comment, reword, "consider ..."), so the backlog grew faster than it was
closed. The review prompt now asks the reviewer to start each follow-up with
``[gap]`` or ``[nit]`` (see the ``known_facts`` in ``deepseek_review.py`` and
``gpt_review.py``). This script rewrites the follow-ups section so that only
bullets tagged ``[gap]`` remain, with the tag removed:

* ``[nit]`` and untagged bullets are dropped: only what the review marks as a
  real gap is filed.
* A ``[gap]`` bullet whose wording is still a nit (a comment, docstring,
  docs, rename, "consider ...") is dropped too.
* The verdict line and anything outside the section are left untouched.

There is no cap on the number of real gaps.

Usage: ``filter_followups.py REVIEW_BODY OUT_FILE``. Writes the filtered review
to ``OUT_FILE`` and prints the number of follow-ups kept.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

_SECTION = re.compile(r"^\s*#{1,6}\s*(?:\d+\.\s*)?suggested follow-?up", re.IGNORECASE)
_NEXT_HEADING = re.compile(r"^\s*#{1,6}\s")
_BULLET = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
_TAG = re.compile(r"^\[(gap|nit)\]\s*", re.IGNORECASE)
_VERDICT = re.compile(r"\b(APPROVE|REQUEST CHANGES)\b")
# Wording that marks a follow-up as a nit even when it is tagged [gap].
_NIT_WORDING = re.compile(
    r"\bconsider(?:ing)?\b"
    r"|\b(?:add|adding|include|leave|write)\b[^.]{0,30}\bcomments?\b"
    r"|\b(?:inline|code|explanatory|brief|short) comments?\b"
    r"|\bdocstrings?\b"
    r"|\bdocumentation\b"
    r"|^document\b"
    r"|\bdocument (?:that|why|how|in|the (?:choice|behaviou?r|contract|decision|asymmetry|semantics))\b"
    r"|\brenam(?:e|es|ed|ing)\b"
    r"|\breword(?:s|ed|ing)?\b"
    r"|\bnits?\b"
    r"|\bcosmetic\b"
    r"|\bstyle\b",
    re.IGNORECASE,
)


def _is_verdict(text: str) -> bool:
    return bool(_VERDICT.search(text)) and "**" in text


def classify(text: str) -> Tuple[bool, str]:
    """``(keep, text without its tag)`` for one follow-up bullet's text."""
    match = _TAG.match(text)
    if not match or match.group(1).lower() != "gap":
        return False, text
    rest = text[match.end() :]
    return not _NIT_WORDING.search(rest), rest


def filter_review(body: str) -> Tuple[str, int]:
    """The review with non-gap follow-ups removed, and how many follow-ups were kept."""
    lines = body.splitlines(keepends=True)
    out: List[str] = []
    kept = 0
    in_section = False
    dropping = False
    bullet_indent = 0
    for line in lines:
        if _SECTION.match(line):
            in_section, dropping = True, False
            out.append(line)
            continue
        if in_section and _NEXT_HEADING.match(line):
            in_section, dropping = False, False
        if not in_section:
            out.append(line)
            continue
        bullet = _BULLET.match(line)
        if bullet and not _is_verdict(line):
            indent, text = bullet.groups()
            keep, rest = classify(text)
            dropping, bullet_indent = not keep, len(indent)
            if keep:
                kept += 1
                out.append(line[: line.index(text)] + rest + ("\n" if line.endswith("\n") else ""))
            continue
        if dropping and line.strip() and len(line) - len(line.lstrip()) > bullet_indent:
            continue  # continuation line of a dropped bullet
        dropping = False
        out.append(line)
    return "".join(out), kept


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} REVIEW_BODY OUT_FILE", file=sys.stderr)
        return 2
    body = Path(argv[1]).read_text(encoding="utf-8")
    filtered, kept = filter_review(body)
    Path(argv[2]).write_text(filtered, encoding="utf-8")
    print(kept)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
