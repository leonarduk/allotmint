"""End-to-end coverage for LOG_FORMAT against the real backend/logging.ini.

The unit tests in ``test_logging_setup.py`` all mock ``logging.config.fileConfig``,
so they never exercise the actual ini file shipped in the repo. This module
loads it for real and asserts on genuine stdout output, closing the gap
flagged independently by issues #5950, #5958, #5962, #5965, #5924, #5970,
#5984 and #5986.
"""

import json
import logging
from pathlib import Path

import backend.logging_setup as logging_setup

REPO_ROOT = Path(__file__).resolve().parents[1]
_RESTORED_LOGGER_NAMES = ("uvicorn", "uvicorn.error", "uvicorn.access")


def _snapshot_logger(logger: logging.Logger) -> dict:
    return {
        "handlers": logger.handlers[:],
        "level": logger.level,
        "propagate": logger.propagate,
        "disabled": logger.disabled,
    }


def _restore_logger(logger: logging.Logger, state: dict) -> None:
    logger.handlers = state["handlers"]
    logger.level = state["level"]
    logger.propagate = state["propagate"]
    logger.disabled = state["disabled"]


def test_real_logging_ini_with_log_format_json_emits_only_valid_json_lines(monkeypatch, capsys):
    """Load the real backend/logging.ini (fileConfig is NOT mocked) with
    LOG_FORMAT=json and verify every line written to real stdout is valid,
    parseable JSON -- no plain-text lines mixed in."""
    root_logger = logging.getLogger()
    restored_loggers = {
        "": root_logger,
        **{name: logging.getLogger(name) for name in _RESTORED_LOGGER_NAMES},
    }
    saved_state = {name: _snapshot_logger(logger) for name, logger in restored_loggers.items()}

    monkeypatch.setattr(logging_setup.config, "log_config", "backend/logging.ini")
    monkeypatch.setattr(logging_setup.config, "repo_root", REPO_ROOT)
    monkeypatch.setattr(logging_setup.config, "log_format", "json")
    root_logger.handlers = []

    try:
        logging_setup.setup_logging()

        emitting_logger = logging.getLogger("app.e2e.json_smoke")
        emitting_logger.info("hello from the end-to-end JSON logging test")

        captured_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]

        assert captured_lines, "expected at least one line written to stdout"
        for line in captured_lines:
            payload = json.loads(line)  # raises ValueError if the line isn't valid JSON
            assert payload["message"] == "hello from the end-to-end JSON logging test"
            assert payload["level"] == "INFO"
            assert payload["logger"] == "app.e2e.json_smoke"
            assert "timestamp" in payload
    finally:
        for name, logger in restored_loggers.items():
            _restore_logger(logger, saved_state[name])
        (REPO_ROOT / "logs" / "backend.log").unlink(missing_ok=True)
