"""AST scanner behind ``tests/test_log_sanitization_audit.py`` and the
``check_new_log_sanitisation.py`` pre-commit hook.

Run it directly to print the current findings in baseline format, e.g. to
regenerate ``tests/data/log_sanitization_baseline.txt`` (re-add the ``#``
justification comments by hand afterwards):

    python scripts/build_tools/_scan_log_sanitisation.py

Each finding is identified by a line-independent *call key* (see
:class:`LogCallFinding`), so edits elsewhere in a file never change the key
of an existing grandfathered call (#8689).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
EXCLUDED_FILES = {BACKEND_ROOT / "logging_setup.py"}
# Logging methods checked for unsanitised user-controlled values.
# `debug` and `exception` were added to cover bare logger.* calls with
# user-controlled values (see PR #5835), alongside the originally-checked
# `info`/`warning`/`error`. To extend the lint to another logging method,
# add it here and update tests/data/log_sanitization_baseline.txt accordingly.
LOG_METHODS = {"warning", "error", "info", "debug", "exception"}
SANITISERS = {"sanitise_log_value", "sanitise_exception_traceback"}
MODULE_SCOPE = "<module>"
KEY_SEPARATOR = "::"


class LogCallFinding(NamedTuple):
    """One logger call with a non-literal, non-sanitised positional argument.

    ``key`` (``rel_path::qualname::call_source``) is what the baseline stores;
    ``lineno`` is kept only for error messages. ``qualname`` is the dotted
    name of the enclosing class/function scope (``<module>`` at top level).
    Two identical calls in the same scope share a key, so the baseline
    repeats that key once per occurrence.
    """

    rel_path: str
    lineno: int
    qualname: str
    call_source: str

    @property
    def key(self) -> str:
        return KEY_SEPARATOR.join((self.rel_path, self.qualname, self.call_source))


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
        if isinstance(func, ast.Name) and func.id in SANITISERS:
            return True
        if isinstance(func, ast.Attribute) and func.attr in SANITISERS:
            return True
    return False


def _is_unwrapped_log_call(node: ast.Call) -> bool:
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr in LOG_METHODS):
        return False
    if not (isinstance(func.value, ast.Name) and func.value.id == "logger"):
        return False
    # args[0] is the format string itself; check the interpolated values.
    return any(not _is_safe_arg(arg) for arg in node.args[1:])


def normalise_call_source(node: ast.Call) -> str:
    """Return a whitespace-collapsed ``ast.unparse`` of ``node``.

    ``ast.unparse`` already discards the original layout (line breaks,
    indentation, trailing commas, quote style); collapsing whitespace keeps
    the key on a single baseline line.
    """

    return " ".join(ast.unparse(node).split())


class _LogCallVisitor(ast.NodeVisitor):
    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.scope: list[str] = []
        self.findings: list[LogCallFinding] = []

    def _visit_scope(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = _visit_scope  # noqa: N815
    visit_AsyncFunctionDef = _visit_scope  # noqa: N815
    visit_ClassDef = _visit_scope  # noqa: N815

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if _is_unwrapped_log_call(node):
            self.findings.append(
                LogCallFinding(
                    rel_path=self.rel_path,
                    lineno=node.lineno,
                    qualname=".".join(self.scope) or MODULE_SCOPE,
                    call_source=normalise_call_source(node),
                )
            )
        self.generic_visit(node)


def find_unwrapped_log_call_findings() -> list[LogCallFinding]:
    """Return a :class:`LogCallFinding` for every logger call in ``backend/``
    with a non-literal, non-sanitised positional argument after the format
    string, ordered by path then line.
    """

    findings: list[LogCallFinding] = []
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        if path in EXCLUDED_FILES or "tests" in path.parts:
            continue
        rel_path = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _LogCallVisitor(rel_path)
        visitor.visit(tree)
        findings.extend(sorted(visitor.findings, key=lambda finding: finding.lineno))
    return findings


def find_unwrapped_log_calls() -> list[tuple[str, int]]:
    """Return ``(relative_path, lineno)`` for every unwrapped logger call.

    Line-based view of :func:`find_unwrapped_log_call_findings`, used by the
    pre-commit hook to match findings against the staged diff's added lines.
    """

    return [(finding.rel_path, finding.lineno) for finding in find_unwrapped_log_call_findings()]


if __name__ == "__main__":
    for key in sorted(finding.key for finding in find_unwrapped_log_call_findings()):
        print(key)
