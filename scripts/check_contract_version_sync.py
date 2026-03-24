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

# Matches a line that is a comment in Python (#) or TypeScript (//)
_COMMENT_LINE = re.compile(r'^\s*(#|//)')


def _display_path(path: Path) -> str:
    """Return a repo-relative path if possible, otherwise the absolute path."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def extract_contract_version(path: Path) -> str:
    """Return the SPA_RESPONSE_CONTRACT_VERSION value from *path*.

    Comment lines (starting with ``#`` or ``//``) are ignored so that
    a commented-out old version does not trigger the duplicate guard or
    shadow the real definition.

    Raises ValueError if the pattern is not found or appears more than once
    on non-comment lines.
    """
    text = path.read_text(encoding="utf-8")
    matches = [
        m
        for line in text.splitlines()
        if not _COMMENT_LINE.match(line)
        for m in VERSION_PATTERN.findall(line)
    ]
    if not matches:
        raise ValueError(
            f"Could not find SPA_RESPONSE_CONTRACT_VERSION in {_display_path(path)}"
        )
    if len(matches) > 1:
        raise ValueError(
            f"Found {len(matches)} occurrences of SPA_RESPONSE_CONTRACT_VERSION in "
            f"{_display_path(path)} — expected exactly one. "
            "Remove or comment out any duplicate definitions."
        )
    # matches[0] is (quote_char, version_string) from the two capture groups
    return matches[0][1]


def main() -> int:
    try:
        python_version = extract_contract_version(PYTHON_CONTRACT)
        typescript_version = extract_contract_version(TYPESCRIPT_CONTRACT)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if python_version != typescript_version:
        print(
            "ERROR: SPA contract version mismatch — "
            f"Python ({_display_path(PYTHON_CONTRACT)}): {python_version!r}, "
            f"TypeScript ({_display_path(TYPESCRIPT_CONTRACT)}): {typescript_version!r}",
            file=sys.stderr,
        )
        return 1

    print(f"OK: SPA contract version in sync ({python_version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
