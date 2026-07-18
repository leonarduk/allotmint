"""One-off helper used to compute the baseline for
``tests/test_log_sanitization_audit.py``. Not part of the test suite itself
-- run manually when auditing a new batch of logger calls:

    python scripts/dev_tools/_scan_log_sanitisation.py
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
EXCLUDED_FILES = {BACKEND_ROOT / "logging_setup.py"}
LOG_METHODS = {"warning", "error", "info"}


def _is_safe_arg(node: ast.expr) -> bool:
    """Return True if ``node`` cannot carry unsanitised external input."""

    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.JoinedStr):
        # f-strings: each interpolated value would need its own check, but
        # none of the current call sites use f-strings for logger args.
        return False
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "sanitise_log_value":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "sanitise_log_value":
            return True
    return False


def find_unwrapped_log_calls() -> list[tuple[str, int]]:
    """Return ``(relative_path, lineno)`` for every logger call with a
    non-literal, non-sanitised positional argument after the format string.
    """

    results: list[tuple[str, int]] = []
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        if path in EXCLUDED_FILES or "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr in LOG_METHODS):
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == "logger"):
                continue
            # args[0] is the format string itself; check the interpolated values.
            for arg in node.args[1:]:
                if not _is_safe_arg(arg):
                    results.append(
                        (str(path.relative_to(REPO_ROOT)).replace("\\", "/"), node.lineno)
                    )
                    break
    return results


if __name__ == "__main__":
    for rel_path, lineno in find_unwrapped_log_calls():
        print(f"{rel_path}:{lineno}")
