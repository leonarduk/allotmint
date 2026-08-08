"""Warn when architecture diagrams cannot be reproduced or are referenced stale.

The check is intentionally advisory: architecture documentation should not make
an otherwise valid change fail CI.  Findings use GitHub workflow annotations so
they remain visible in a pull request's log.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Build this value from fragments so the audit does not report its own source.
LEGACY_DIAGRAM = "docs/" + "aws-architecture.svg"
LEGACY_DIAGRAM_PATH = Path(LEGACY_DIAGRAM)
SCRIPT_SUFFIXES = frozenset({".js", ".mjs", ".ps1", ".py", ".sh", ".ts"})
# Formats that legitimately hold non-UTF-8 bytes; scanning them for a text
# reference always fails, so they are skipped rather than reported as unreadable.
BINARY_SUFFIXES = frozenset({".gif", ".ico", ".jpg", ".jpeg", ".parquet", ".pdf", ".png", ".svg"})


def _normalise_name(value: str) -> str:
    """Return a filename fragment suitable for convention comparisons."""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def tracked_files(root: Path) -> list[Path]:
    """Return repository-relative files tracked by Git."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [Path(name) for name in result.stdout.split("\0") if name]


def has_regenerator(diagram: Path, files: list[Path]) -> bool:
    """Return whether a tracked script follows the diagram generator convention."""
    diagram_name = _normalise_name(diagram.stem)
    for path in files:
        if path.suffix.lower() not in SCRIPT_SUFFIXES:
            continue
        script_name = _normalise_name(path.stem)
        if "generate" in script_name and diagram_name in script_name:
            return True
    return False


def find_unreproducible_diagrams(files: list[Path]) -> list[Path]:
    """Find architecture SVGs without a conventionally named generator."""
    diagrams = [
        path
        for path in files
        if path.suffix.lower() == ".svg" and "architecture" in path.stem.lower()
    ]
    return [path for path in diagrams if not has_regenerator(path, files)]


def _legacy_reference_variants(path: Path) -> frozenset[str]:
    """Return the substrings that indicate `path` references the legacy diagram.

    A file living alongside the diagram (i.e. also under `docs/`) may link to
    it with a sibling-relative path such as `aws-architecture.svg` or
    `./aws-architecture.svg`, not just the repository-root spelling.
    """
    variants = {LEGACY_DIAGRAM, f"/{LEGACY_DIAGRAM}"}
    if path.parent == LEGACY_DIAGRAM_PATH.parent:
        variants.add(LEGACY_DIAGRAM_PATH.name)
        variants.add(f"./{LEGACY_DIAGRAM_PATH.name}")
    return frozenset(variants)


def find_stale_legacy_references(root: Path, files: list[Path]) -> tuple[list[Path], list[Path]]:
    """Find non-README files that refer to the removed legacy AWS diagram.

    Returns a `(stale, unreadable)` pair: `unreadable` lists tracked candidate
    files that could not be scanned, so an incomplete scan stays visible
    instead of silently reporting zero warnings.
    """
    if (root / LEGACY_DIAGRAM).exists():
        return [], []

    stale: list[Path] = []
    unreadable: list[Path] = []
    for path in files:
        if path.name.lower().startswith("readme") or path.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            content = (root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            unreadable.append(path)
            continue
        if any(variant in content for variant in _legacy_reference_variants(path)):
            stale.append(path)
    return stale, unreadable


def main() -> int:
    """Run advisory architecture-documentation checks."""
    files = tracked_files(ROOT)
    findings = 0

    for diagram in find_unreproducible_diagrams(files):
        findings += 1
        print(
            f"::warning file={diagram}::Static architecture diagram has no "
            "regeneration script. Add a script named "
            f"generate_{diagram.stem.replace('-', '_')} with a supported script suffix."
        )

    stale_references, unreadable_candidates = find_stale_legacy_references(ROOT, files)

    for reference in stale_references:
        findings += 1
        print(
            f"::warning file={reference}::Stale reference to removed "
            f"{LEGACY_DIAGRAM}. Update or remove the reference."
        )

    for path in unreadable_candidates:
        findings += 1
        print(
            f"::warning file={path}::Could not scan for a stale reference to "
            f"{LEGACY_DIAGRAM}; the file is not valid UTF-8 text."
        )

    print(f"Architecture diagram audit complete ({findings} warning(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
