"""Regression guard for broken doc links referenced from code comments (issue #5995).

Scans source files (Python, TypeScript/TSX, PowerShell, and GitHub Actions
YAML -- the file types that actually carry these "see docs/FOO.md" comments
in this repo) for a docs-relative markdown reference and asserts the
referenced file exists on disk. Case-sensitive, since CI runs on Linux where
two differently-cased paths are different files even though a local
Windows/macOS checkout would silently resolve either.

``tests/`` is excluded: fixtures there intentionally reference nonexistent
doc paths (e.g. placeholder names in classify_change tests), so scanning it
would produce false positives unrelated to real documentation drift.

An optional anchor fragment after the filename is stripped before the
existence check -- anchors aren't verified, only the file.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_SCAN_EXTENSIONS = (".py", ".ts", ".tsx", ".ps1", ".yml", ".yaml")

_EXCLUDED_DIR_PARTS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    ".venv-lambda",
    "coverage",
    "htmlcov",
    "docs",  # only code comments are in scope, not doc-to-doc links
    "tests",  # fixtures intentionally use nonexistent placeholder doc names
}

# Matches `docs/some/path.md`, optionally followed by a `#anchor` fragment.
# Deliberately excludes `*`, spaces, and other glob/prose characters so
# generic phrases like "docs/*.md" or "the docs/ folder" don't match.
_DOC_REF_PATTERN = re.compile(r"docs/[A-Za-z0-9_./\-]+\.md(?:#[A-Za-z0-9_\-]+)?")


def _iter_scanned_files():
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in _SCAN_EXTENSIONS:
            continue
        if _EXCLUDED_DIR_PARTS & set(path.relative_to(REPO_ROOT).parts):
            continue
        yield path


def _find_missing_doc_references() -> list[str]:
    missing = []
    for path in _iter_scanned_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in _DOC_REF_PATTERN.finditer(line):
                doc_ref = match.group(0).split("#", 1)[0]
                if not (REPO_ROOT / doc_ref).is_file():
                    missing.append(f"{rel_path}:{lineno}: {doc_ref}")
    return missing


def test_docs_referenced_in_code_comments_exist() -> None:
    missing = _find_missing_doc_references()
    assert not missing, (
        "Code comment(s) reference a docs/*.md file that doesn't exist "
        "(fix the path or add the missing doc):\n" + "\n".join(sorted(missing))
    )
