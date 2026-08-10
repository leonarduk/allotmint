"""Regression guard for CWE-117 log injection (issue #4997).

Scans every ``logger.warning/error/info/debug/exception`` call in ``backend/`` for
positional arguments (after the format string) that are neither literals
nor wrapped in ``sanitise_log_value(...)``. A large baseline of pre-existing
call sites is grandfathered in via ``tests/data/log_sanitization_baseline.txt``
(most are internal-only data or already-safe ``%r``/``str(exc)`` patterns
that the AST scan can't distinguish without full dataflow analysis).

The test only fails on *new* unwrapped call sites that aren't in the
baseline -- i.e. it's a ratchet, not a full enforcement of every existing
call. Adding a new logger call with a variable argument requires either
wrapping it in ``sanitise_log_value`` or, if the value is provably internal
(e.g. a loop counter), adding the ``file:line`` to the baseline file with a
comment explaining why.
"""

from __future__ import annotations

from pathlib import Path

from scripts.build_tools import _scan_log_sanitisation
from scripts.build_tools._scan_log_sanitisation import find_unwrapped_log_calls

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "tests" / "data" / "log_sanitization_baseline.txt"


def _load_baseline() -> set[str]:
    lines = BASELINE_PATH.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def test_no_new_unwrapped_logger_calls() -> None:
    baseline = _load_baseline()
    current = {f"{rel_path}:{lineno}" for rel_path, lineno in find_unwrapped_log_calls()}

    new_entries = current - baseline
    assert not new_entries, (
        "New logger.warning/error/info call(s) with an unsanitised argument found:\n"
        + "\n".join(sorted(new_entries))
        + "\n\nWrap user-controlled values in sanitise_log_value(...) from "
        "backend.logging_setup, or add the file:line to "
        "tests/data/log_sanitization_baseline.txt with a comment explaining "
        "why the value can't carry attacker-controlled input."
    )


def test_find_unwrapped_log_calls_flags_multi_line_debug_and_exception_calls(monkeypatch, tmp_path) -> None:
    """Multi-line logger.debug/exception calls with unsanitised args must be detected (#5836).

    LOG_METHODS already includes "debug" and "exception", but no test
    previously fed synthetic source through the scanner to confirm a call
    whose arguments span several lines is still flagged with the correct
    node.lineno (the line the call *starts* on).
    """
    fake_backend = tmp_path / "backend"
    fake_backend.mkdir()
    source = (
        "import logging\n"
        "\n"
        "logger = logging.getLogger(__name__)\n"
        "\n"
        "\n"
        "def handler(owner):\n"
        "    logger.debug(\n"
        "        'owner lookup failed for %s',\n"
        "        owner,\n"
        "    )\n"
        "    logger.exception(\n"
        "        'unexpected error for %s',\n"
        "        owner,\n"
        "    )\n"
    )
    (fake_backend / "multiline_example.py").write_text(source, encoding="utf-8")

    monkeypatch.setattr(_scan_log_sanitisation, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(_scan_log_sanitisation, "BACKEND_ROOT", fake_backend)
    monkeypatch.setattr(_scan_log_sanitisation, "EXCLUDED_FILES", set())

    results = find_unwrapped_log_calls()

    assert ("backend/multiline_example.py", 7) in results
    assert ("backend/multiline_example.py", 11) in results


def test_warning_and_error_exception_messages_are_sanitised() -> None:
    """Exception text logged at warning/error level must remain on one line (#5362)."""
    import ast

    violations: list[str] = []

    class ExceptionLogVisitor(ast.NodeVisitor):
        def __init__(self, relative_path: Path) -> None:
            self.relative_path = relative_path
            self.exception_names: list[str] = []

        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802
            if node.name is None:
                self.generic_visit(node)
                return
            self.exception_names.append(node.name)
            self.generic_visit(node)
            self.exception_names.pop()

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            is_relevant_log = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in {"warning", "error"}
                and bool(self.exception_names)
            )
            if is_relevant_log:
                for argument in node.args[1:]:
                    uses_exception = any(
                        isinstance(child, ast.Name) and child.id in self.exception_names for child in ast.walk(argument)
                    )
                    is_sanitised = any(
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id in {"sanitise_log_value", "_sanitize_for_log"}
                        for child in ast.walk(argument)
                    )
                    if uses_exception and not is_sanitised:
                        violations.append(f"{self.relative_path}:{node.lineno}")
            self.generic_visit(node)

    for source_path in sorted((REPO_ROOT / "backend").rglob("*.py")):
        relative_path = source_path.relative_to(REPO_ROOT)
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(relative_path))
        ExceptionLogVisitor(relative_path).visit(tree)

    assert (
        not violations
    ), "logger.warning/error exception argument(s) must be wrapped in " "sanitise_log_value(...):\n" + "\n".join(
        violations
    )
