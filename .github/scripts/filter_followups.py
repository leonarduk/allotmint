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
* A ``[gap]`` bullet whose main ask is still a nit (it opens with "consider",
  "add a comment", "rename", "reword" and similar) is dropped too.
* Nested sub-bullets follow their parent follow-up.
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
# Wording that marks a follow-up as a nit even when it is tagged [gap]. It only
# counts when it opens the follow-up (its main ask): "Add a comment ..., and
# reject rows with a NULL owner" or "Document the retry contract so clients
# don't double-submit" mention the same words but ask for more than a nit.
_NIT_OPENING = re.compile(
    r"^(?:"
    r"consider(?:ing)?\b"
    r"|(?:add|adding|include|leave|write)\s+(?:an?\s+)?(?:brief\s+|short\s+|inline\s+|code\s+|explanatory\s+)?(?:comment|docstring|note)s?\b"
    r"|(?:update|tighten|expand)\s+(?:the\s+)?docstrings?\b"
    r"|document\s+(?:that|why|how|in)\b"
    r"|renam(?:e|ing)\b"
    r"|reword(?:ing)?\b"
    r"|(?:style|cosmetic|nit)\b"
    r")",
    re.IGNORECASE,
)
# A second clause ("..., and reject rows with a NULL owner") means the
# follow-up asks for more than the nit it opens with.
_SECOND_ASK = re.compile(r"(?:,|;)\s*(?:and|also|then)\s+\w+|;\s+\w+")
# The review's verdict line, e.g. "- `**APPROVE**` — ..." or "**REQUEST CHANGES** — ...".
_VERDICT_LINE = re.compile(r"^\s*(?:[-*+]\s+)?`?\*\*(?:APPROVE|REQUEST CHANGES)\*\*")


def _is_verdict(line: str) -> bool:
    return bool(_VERDICT_LINE.match(line))


def classify(text: str) -> Tuple[bool, str]:
    """``(keep, text without its tag)`` for one follow-up bullet's text."""
    match = _TAG.match(text)
    if not match or match.group(1).lower() != "gap":
        return False, text
    rest = text[match.end() :]
    nit_opening = bool(_NIT_OPENING.match(rest.lstrip("`*_ ")))
    return not nit_opening or bool(_SECOND_ASK.search(rest)), rest


def filter_review(body: str) -> Tuple[str, int]:
    """The review with non-gap follow-ups removed, and how many follow-ups were kept."""
    lines = body.splitlines(keepends=True)
    out: List[str] = []
    kept = 0
    in_section = False
    dropping = False
    parent_seen = False
    bullet_indent = 0
    for line in lines:
        if _SECTION.match(line):
            in_section, dropping, parent_seen = True, False, False
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
            if parent_seen and len(indent) > bullet_indent:
                # A nested sub-bullet belongs to its parent follow-up.
                if not dropping:
                    out.append(line)
                continue
            keep, rest = classify(text)
            parent_seen = True
            dropping, bullet_indent = not keep, len(indent)
            if keep:
                kept += 1
                out.append(line[: line.index(text)] + rest + ("\n" if line.endswith("\n") else ""))
            continue
        if dropping and line.strip() and len(line) - len(line.lstrip()) > bullet_indent:
            continue  # continuation line of a dropped bullet
        if line.strip():
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
