"""Regression guard for CWE-117 log injection (issue #4997).

Scans every ``logger.warning/error/info/debug/exception`` call in ``backend/`` for
positional arguments (after the format string) that are neither literals
nor wrapped in ``sanitise_log_value(...)``. A large baseline of pre-existing
call sites is grandfathered in via ``tests/data/log_sanitization_baseline.txt``
(most are internal-only data or already-safe ``%r``/``str(exc)`` patterns
that the AST scan can't distinguish without full dataflow analysis).

Baseline entries are keyed on line-independent call identity,
``path::enclosing_qualname::normalised call source`` (#8689), so adding or
removing lines elsewhere in a file never turns a grandfathered call into a
false positive. Identical calls in the same scope are counted: the baseline
lists the key once per occurrence.

The test only fails on *new* unwrapped call sites that aren't in the
baseline -- i.e. it's a ratchet, not a full enforcement of every existing
call. Adding a new logger call with a variable argument requires either
wrapping it in ``sanitise_log_value`` or, if the value is provably internal
(e.g. a loop counter), adding its key (as printed in the failure message, or
by ``python scripts/build_tools/_scan_log_sanitisation.py``) to the baseline
file with a comment explaining why.

The ratchet also runs in reverse (#7702): a baseline entry that no longer
matches any current call site (because the call was removed, sanitised, or
edited) fails the test, so dead exemptions are pruned instead of lingering
and silently grandfathering a later unsafe call that happens to share the key.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from scripts.build_tools import _scan_log_sanitisation
from scripts.build_tools._scan_log_sanitisation import (
    LogCallFinding,
    find_unwrapped_log_call_findings,
    find_unwrapped_log_calls,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "tests" / "data" / "log_sanitization_baseline.txt"


def _load_baseline(path: Path = BASELINE_PATH) -> Counter[str]:
    """Return how many times each call key is listed in the baseline file."""

    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return Counter(line for line in lines if line and not line.startswith("#"))


def _unbaselined_findings(findings: list[LogCallFinding], baseline: Counter[str]) -> list[LogCallFinding]:
    """Return findings whose key occurs more often than the baseline allows.

    When a key is over its baselined count, every occurrence of it is
    returned, since there's no line-independent way to tell which one is new.
    """

    excess = Counter(finding.key for finding in findings) - baseline
    return [finding for finding in findings if finding.key in excess]


def _stale_baseline_keys(findings: list[LogCallFinding], baseline: Counter[str]) -> Counter[str]:
    """Return baseline keys (with surplus counts) that no current call accounts for."""

    return baseline - Counter(finding.key for finding in findings)


def _format_findings(findings: list[LogCallFinding], baseline: Counter[str]) -> str:
    current = Counter(finding.key for finding in findings)
    lines = []
    for finding in findings:
        allowed = baseline[finding.key]
        note = f" (found {current[finding.key]}, baseline allows {allowed})" if allowed else ""
        lines.append(f"{finding.rel_path}:{finding.lineno}{note}\n    key: {finding.key}")
    return "\n".join(lines)


def test_no_new_unwrapped_logger_calls() -> None:
    baseline = _load_baseline()
    findings = find_unwrapped_log_call_findings()
    new_findings = _unbaselined_findings(findings, baseline)

    assert not new_findings, (
        "New logger.warning/error/info/debug/exception call(s) with an unsanitised argument found:\n"
        + _format_findings(new_findings, baseline)
        + "\n\nWrap user-controlled values in sanitise_log_value(...) from "
        "backend.logging_setup, or add the key line(s) above to "
        "tests/data/log_sanitization_baseline.txt (sorted, with a # comment "
        "explaining why the value can't carry attacker-controlled input). "
        "`python scripts/build_tools/_scan_log_sanitisation.py` prints every "
        "current key."
    )


def test_baseline_has_no_stale_entries() -> None:
    """Every baseline entry must still match a current call site (#7702)."""

    stale = _stale_baseline_keys(find_unwrapped_log_call_findings(), _load_baseline())

    assert not stale, (
        "tests/data/log_sanitization_baseline.txt lists exemption(s) that match no "
        "current unsanitised logger call (the call was removed, sanitised, or "
        "edited). Delete these lines (and their # comment, if any):\n"
        + "\n".join(f"    {key} (x{count})" if count > 1 else f"    {key}" for key, count in sorted(stale.items()))
    )


def _point_scanner_at(monkeypatch, tmp_path: Path) -> Path:
    fake_backend = tmp_path / "backend"
    fake_backend.mkdir()
    monkeypatch.setattr(_scan_log_sanitisation, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(_scan_log_sanitisation, "BACKEND_ROOT", fake_backend)
    monkeypatch.setattr(_scan_log_sanitisation, "EXCLUDED_FILES", set())
    return fake_backend


_GRANDFATHERED_SOURCE = (
    "import logging\n"
    "\n"
    "logger = logging.getLogger(__name__)\n"
    "\n"
    "\n"
    "class Store:\n"
    "    def load(self, path):\n"
    "        logger.warning('read failed for %s', path)\n"
    "        logger.warning('read failed for %s', path)\n"
    "\n"
    "\n"
    "def handler(owner):\n"
    "    logger.debug(\n"
    "        'owner lookup failed for %s',\n"
    "        owner,\n"
    "    )\n"
)
_DUPLICATE_KEY = "backend/example.py::Store.load::logger.warning('read failed for %s', path)"


def test_baseline_survives_lines_shifting_above_grandfathered_calls(monkeypatch, tmp_path) -> None:
    """Inserting lines above a grandfathered call must not flag it as new (#8689)."""

    fake_backend = _point_scanner_at(monkeypatch, tmp_path)
    module = fake_backend / "example.py"
    module.write_text(_GRANDFATHERED_SOURCE, encoding="utf-8")
    baseline_file = tmp_path / "baseline.txt"
    keys = sorted(finding.key for finding in find_unwrapped_log_call_findings())
    baseline_file.write_text("# comment lines are ignored\n" + "\n".join(keys) + "\n", encoding="utf-8")
    baseline = _load_baseline(baseline_file)
    assert sum(baseline.values()) == 3
    assert baseline[_DUPLICATE_KEY] == 2

    shifted = _GRANDFATHERED_SOURCE.replace("import logging\n", "import logging\n" + "\n" * 5, 1)
    # Re-wrapping the multi-line call onto one line doesn't change its key either.
    shifted = shifted.replace(
        "logger.debug(\n        'owner lookup failed for %s',\n        owner,\n    )",
        'logger.debug("owner lookup failed for %s", owner)',
    )
    module.write_text(shifted, encoding="utf-8")

    findings = find_unwrapped_log_call_findings()
    assert [finding.lineno for finding in findings] == [13, 14, 18]
    assert _unbaselined_findings(findings, baseline) == []


def test_baseline_still_flags_genuinely_new_unwrapped_calls(monkeypatch, tmp_path) -> None:
    """A new unwrapped call -- including an extra copy of a baselined duplicate -- must fail."""

    fake_backend = _point_scanner_at(monkeypatch, tmp_path)
    module = fake_backend / "example.py"
    module.write_text(_GRANDFATHERED_SOURCE, encoding="utf-8")
    baseline = Counter(finding.key for finding in find_unwrapped_log_call_findings())

    module.write_text(
        _GRANDFATHERED_SOURCE + "    logger.exception(\n        'unexpected error for %s',\n        owner,\n    )\n",
        encoding="utf-8",
    )
    new_findings = _unbaselined_findings(find_unwrapped_log_call_findings(), baseline)
    assert [(finding.lineno, finding.key) for finding in new_findings] == [
        (17, "backend/example.py::handler::logger.exception('unexpected error for %s', owner)")
    ]
    assert "backend/example.py:17\n" in _format_findings(new_findings, baseline)

    tripled = _GRANDFATHERED_SOURCE.replace(
        "        logger.warning('read failed for %s', path)\n" * 2,
        "        logger.warning('read failed for %s', path)\n" * 3,
        1,
    )
    module.write_text(tripled, encoding="utf-8")
    new_findings = _unbaselined_findings(find_unwrapped_log_call_findings(), baseline)
    assert [finding.lineno for finding in new_findings] == [8, 9, 10]
    assert {finding.key for finding in new_findings} == {_DUPLICATE_KEY}
    assert "found 3, baseline allows 2" in _format_findings(new_findings, baseline)


def test_stale_baseline_keys_reports_entries_with_no_matching_call(monkeypatch, tmp_path) -> None:
    """Removing or sanitising a baselined call must surface its now-dead entry (#7702)."""

    fake_backend = _point_scanner_at(monkeypatch, tmp_path)
    module = fake_backend / "example.py"
    module.write_text(_GRANDFATHERED_SOURCE, encoding="utf-8")
    baseline = Counter(finding.key for finding in find_unwrapped_log_call_findings())
    assert _stale_baseline_keys(find_unwrapped_log_call_findings(), baseline) == Counter()

    # Drop one of the two duplicate calls, and sanitise handler()'s call.
    edited = _GRANDFATHERED_SOURCE.replace("        logger.warning('read failed for %s', path)\n", "", 1)
    edited = edited.replace("        owner,\n", "        sanitise_log_value(owner),\n")
    module.write_text(edited, encoding="utf-8")

    assert _stale_baseline_keys(find_unwrapped_log_call_findings(), baseline) == Counter(
        {
            _DUPLICATE_KEY: 1,
            "backend/example.py::handler::logger.debug('owner lookup failed for %s', owner)": 1,
        }
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
                sanitiser_names = {
                    "sanitise_log_value",
                    "sanitise_exception_traceback",
                    "_sanitize_for_log",
                }

                class UnsafeExceptionReference(ast.NodeVisitor):
                    found = False

                    def visit_Call(self, child: ast.Call) -> None:  # noqa: N802
                        if isinstance(child.func, ast.Name) and child.func.id in sanitiser_names:
                            return
                        self.generic_visit(child)

                    def visit_Name(self, child: ast.Name) -> None:  # noqa: N802
                        if child.id in self_exception_names:
                            self.found = True

                self_exception_names = self.exception_names
                for argument in node.args:
                    reference = UnsafeExceptionReference()
                    reference.visit(argument)
                    if reference.found:
                        violations.append(f"{self.relative_path}:{node.lineno}")

                raw_traceback = any(
                    keyword.arg == "exc_info"
                    and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is False)
                    for keyword in node.keywords
                )
                if raw_traceback:
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
