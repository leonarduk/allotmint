"""Check that SPA_RESPONSE_CONTRACT_VERSION is identical in the Python backend
contract file and the TypeScript frontend contract file.

Usage::

    python scripts/check_contract_version_sync.py

Exits 0 on success, 1 on mismatch or if the version string cannot be found.

This script intentionally uses only the Python standard library so it can run
in CI before any pip install step.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# These paths are load-bearing constants: the files they point to must remain
# stable. If either file is moved or renamed, update these paths and the CI
# steps that invoke this script.
PYTHON_CONTRACT = ROOT / "backend" / "contracts_spa.py"
TYPESCRIPT_CONTRACT = ROOT / "frontend" / "src" / "contracts" / "spa.ts"

# Backreference \1 enforces that the closing quote matches the opening quote,
# so SPA_RESPONSE_CONTRACT_VERSION = "1.0' does NOT produce a match.
VERSION_PATTERN = re.compile(
    r'SPA_RESPONSE_CONTRACT_VERSION\s*=\s*(["\'])([^"\']+)\1'
)

# Lines whose first non-whitespace token is a comment delimiter are skipped
# entirely so that a full-line comment like:
#   # SPA_RESPONSE_CONTRACT_VERSION = '0.9'  (old)
# does not interfere with the real definition.
_COMMENT_LINE = re.compile(r'^\s*(#|//)')

# Strips trailing inline comments from a non-comment line so that:
#   SPA_RESPONSE_CONTRACT_VERSION = "1.0"  # was SPA_RESPONSE_CONTRACT_VERSION = "0.9"
# doesn't produce two matches from a single line.
# Strategy: remove everything after the first # (Python) or // (TypeScript)
# that is preceded by whitespace, which avoids stripping URLs inside strings.
_INLINE_COMMENT = re.compile(r'\s+(#|//).*$')


def _display_path(path: Path) -> str:
    """Return a repo-relative path if possible, otherwise the absolute path."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def extract_contract_version(path: Path) -> str:
    """Return the SPA_RESPONSE_CONTRACT_VERSION value from *path*.

    Full-line comments (lines starting with ``#`` or ``//``) are skipped.
    Inline trailing comments are stripped before matching so that a comment
    like ``# bumped from SPA_RESPONSE_CONTRACT_VERSION = "0.9"`` on the same
    line as the real definition does not trigger the duplicate guard.

    Raises ValueError if the pattern is not found or appears more than once
    on non-comment lines.
    """
    text = path.read_text(encoding="utf-8")
    matches = [
        m
        for line in text.splitlines()
        if not _COMMENT_LINE.match(line)
        for m in VERSION_PATTERN.findall(_INLINE_COMMENT.sub("", line))
    ]
    if not matches:
        raise ValueError(
            f"Could not find SPA_RESPONSE_CONTRACT_VERSION in {_display_path(path)}"
        )
    if len(matches) > 1:
        raise ValueError(
            f"Found {len(matches)} occurrences of SPA_RESPONSE_CONTRACT_VERSION in "
            f"{_display_path(path)} \u2014 expected exactly one. "
            "Remove or comment out any duplicate definitions."
        )
    # matches[0] is (quote_char, version_string) from the two capture groups
    _, version = matches[0]
    return version


def main() -> int:
    try:
        python_version = extract_contract_version(PYTHON_CONTRACT)
        typescript_version = extract_contract_version(TYPESCRIPT_CONTRACT)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if python_version != typescript_version:
        print(
            "ERROR: SPA contract version mismatch \u2014 "
            f"Python ({_display_path(PYTHON_CONTRACT)}): {python_version!r}, "
            f"TypeScript ({_display_path(TYPESCRIPT_CONTRACT)}): {typescript_version!r}",
            file=sys.stderr,
        )
        return 1

    print(f"OK: SPA contract version in sync ({python_version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
