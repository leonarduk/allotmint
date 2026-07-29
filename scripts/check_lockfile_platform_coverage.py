"""Check that npm lockfiles retain optional dependencies for every OS platform.

Usage::

    python scripts/check_lockfile_platform_coverage.py

Exits 0 on success, 1 if a lockfile is missing optional-dependency entries for
one of the required platforms.

Background: several npm dependencies (esbuild, @emnapi/*, etc.) ship
platform-specific optional packages tagged with an "os" field in
package-lock.json (e.g. "linux", "win32", "darwin"). GitHub Actions installs
these lockfiles with `npm ci` on ubuntu-latest (see
.github/actions/setup-frontend-deps/action.yml), so the "linux" entries must
always be present. Regenerating a lockfile with `npm install` on Windows can
silently prune optional entries for platforms other than the one npm ran on,
which then breaks `npm ci` in CI. This script fails fast, in CI or locally,
before that broken lockfile reaches Linux CI.

This script intentionally uses only the Python standard library so it can run
in CI before any pip install step.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Every lockfile that ships optional platform-specific packages must retain
# entries for at least these three OSes: "linux" is required because CI runs
# `npm ci` on ubuntu-latest; "win32" and "darwin" are required because
# contributors develop locally on Windows and macOS.
REQUIRED_PLATFORMS = frozenset({"linux", "win32", "darwin"})

LOCKFILES = (
    ROOT / "package-lock.json",
    ROOT / "frontend" / "package-lock.json",
)


def platforms_in_lockfile(lockfile: Path) -> set[str]:
    """Return the union of "os" values across optional packages in *lockfile*."""
    data = json.loads(lockfile.read_text(encoding="utf-8"))
    platforms: set[str] = set()
    for pkg in data.get("packages", {}).values():
        if isinstance(pkg, dict) and pkg.get("optional") and "os" in pkg:
            platforms.update(pkg["os"])
    return platforms


def main() -> int:
    failures: list[str] = []
    for lockfile in LOCKFILES:
        if not lockfile.exists():
            continue
        platforms = platforms_in_lockfile(lockfile)
        if not platforms:
            # No platform-restricted optional packages at all in this
            # lockfile; nothing to check.
            continue
        missing = REQUIRED_PLATFORMS - platforms
        if missing:
            try:
                rel = lockfile.relative_to(ROOT)
            except ValueError:
                rel = lockfile
            failures.append(
                f"{rel}: missing optional-dependency entries for "
                f"{sorted(missing)} (found {sorted(platforms)}). This "
                "usually means the lockfile was regenerated with `npm "
                "install` on a single OS, which can prune platform-specific "
                "optional packages for other platforms. Regenerate with "
                "`npm install` (not `npm ci`) and diff against the previous "
                "lockfile to confirm the other platforms' entries are still "
                "present, or restore them from the previous commit."
            )

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 1

    print(f"Lockfile platform coverage OK ({len(LOCKFILES)} lockfiles checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
