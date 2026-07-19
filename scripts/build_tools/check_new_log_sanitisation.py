"""Pre-commit hook: fail if the staged diff adds a new unwrapped logger call.

Reuses the same detection logic as tests/test_log_sanitization_audit.py
(``find_unwrapped_log_calls``), but restricts violations to lines newly
added by the staged diff. This means the 133+ pre-existing grandfathered
entries in tests/data/log_sanitization_baseline.txt never block a commit --
only a genuinely new unwrapped logger call does, even in an otherwise
untouched file. See issue #5262.

Run manually against currently staged changes:
    python scripts/build_tools/check_new_log_sanitisation.py <file> [<file> ...]

Wired into .pre-commit-config.yaml as a `local` hook with pass_filenames
enabled (the default), so pre-commit passes it the staged Python files.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.build_tools._scan_log_sanitisation import find_unwrapped_log_calls  # noqa: E402


def _added_line_numbers(path: str, *, cwd: Path = REPO_ROOT) -> set[int]:
    """Return the line numbers added to ``path`` by the currently staged diff."""

    result = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--", path],
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
    )

    added: set[int] = set()
    next_line: int | None = None
    for line in result.stdout.splitlines():
        if line.startswith("@@"):
            # "@@ -a,b +c,d @@ ..." -- c is the first new-file line number
            # this hunk touches; -U0 means only +/- lines follow, no context.
            hunk_header = line.split("@@")[1].strip()
            plus_part = hunk_header.split(" ")[1]
            next_line = int(plus_part[1:].split(",")[0])
        elif line.startswith("+++") or line.startswith("---"):
            continue
        elif line.startswith("+"):
            if next_line is None:  # pragma: no cover - malformed diff, be defensive
                continue
            added.add(next_line)
            next_line += 1
        # A "-" line removes a line from the old file; it does not advance
        # the new-file line counter, so next_line is left untouched.
    return added


def _is_backend_python_file(path: str) -> bool:
    normalised = path.replace("\\", "/")
    if not normalised.endswith(".py"):
        return False
    if not normalised.startswith("backend/"):
        return False
    if normalised == "backend/logging_setup.py":
        return False
    if "/tests/" in normalised or normalised.startswith("tests/"):
        return False
    return True


def main(argv: list[str]) -> int:
    candidate_files = [f for f in argv if _is_backend_python_file(f)]
    if not candidate_files:
        return 0

    added_lines_by_file = {f: _added_line_numbers(f) for f in candidate_files}
    candidate_files_set = set(candidate_files)

    violations: list[str] = []
    for rel_path, lineno in find_unwrapped_log_calls():
        if rel_path not in candidate_files_set:
            continue
        if lineno in added_lines_by_file[rel_path]:
            violations.append(f"{rel_path}:{lineno}")

    if violations:
        print(
            "New logger.warning/error/info call(s) with an unsanitised argument:",
            file=sys.stderr,
        )
        for v in sorted(violations):
            print(f"  {v}", file=sys.stderr)
        print(
            "\nWrap user-controlled values in sanitise_log_value(...) from " "backend.logging_setup.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
