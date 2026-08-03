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
