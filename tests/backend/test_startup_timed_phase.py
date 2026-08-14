"""Coverage for ``_timed_phase`` (backend/bootstrap/startup.py) and its
interaction with ``sanitise_log_value`` / structured logging (issue #5343,
tracked under the consolidated coverage issue #5974).

``_timed_phase`` is the context manager cold-start warmup phases are wrapped
in (see ``AppLifecycleService._warm_snapshot``). It must:

* log the phase's duration even when the wrapped code raises, without
  swallowing the exception (a bug here would hide startup failures behind a
  generic 500 with no diagnostic signal);
* attach ``phase``/``duration_ms`` as structured ``extra`` fields so a JSON
  log formatter (not configured today, but anticipated by the docstring on
  ``_timed_phase``) can serialize them without extra plumbing;
* tolerate a ``None`` or non-string phase name via ``sanitise_log_value``
  rather than raising while trying to log.
"""

from __future__ import annotations

import json
import logging

import pytest

from backend.bootstrap.startup import _timed_phase
from backend.logging_setup import sanitise_log_value

_LOGGER_NAME = "backend.bootstrap.startup"


def test_timed_phase_logs_duration_and_reraises_on_exception(
    caplog: pytest.LogCaptureFixture,
):
    """A phase that raises must still get its duration logged, and the
    exception must propagate (not be swallowed by the context manager)."""
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        with pytest.raises(ValueError, match="boom"):
            with _timed_phase("exploding_phase"):
                raise ValueError("boom")

    phase_records = [record for record in caplog.records if getattr(record, "phase", None) == "exploding_phase"]
    assert len(phase_records) == 1, "Expected exactly one 'cold_start_phase' log for the failing phase, got: " + str(
        [r.message for r in caplog.records]
    )
    record = phase_records[0]
    assert record.levelno == logging.INFO
    assert "cold_start_phase" in record.message
    assert isinstance(record.duration_ms, float)
    assert record.duration_ms >= 0


def test_timed_phase_handles_none_and_non_string_names(
    caplog: pytest.LogCaptureFixture,
):
    """sanitise_log_value must coerce a None/non-string phase name to text
    instead of raising while _timed_phase logs the completion message."""
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        with _timed_phase(None):
            pass
        with _timed_phase(12345):
            pass

    # sanitise_log_value itself must not raise for these inputs.
    assert sanitise_log_value(None) == "None"
    assert sanitise_log_value(12345) == "12345"

    phases = [getattr(record, "phase", "missing") for record in caplog.records]
    assert None in phases
    assert 12345 in phases
    # No exception should have interrupted the two context managers above;
    # both completions must have logged successfully.
    assert len(caplog.records) == 2


def test_timed_phase_exception_phase_name_is_sanitised(caplog: pytest.LogCaptureFixture):
    """A phase name containing CRLF (log-injection attempt, CWE-117) must be
    sanitised in the rendered message even when the wrapped code raises."""
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        with pytest.raises(RuntimeError):
            with _timed_phase("bad\r\nname"):
                raise RuntimeError("fail")

    record = next(r for r in caplog.records if "phase=" in r.message)
    assert "\r" not in record.message
    assert "\n" not in record.message
    # The raw (unsanitised) value is still present in `extra` for consumers
    # that want the structured field rather than the rendered text.
    assert record.phase == "bad\r\nname"


def test_timed_phase_structured_logging_serializes_to_json():
    """When a JSON formatter is attached, the `extra={"phase", "duration_ms"}`
    fields _timed_phase supplies must serialize to valid JSON with the
    expected keys -- this is the scenario the docstring on _timed_phase calls
    out ("whenever a JSON log formatter is in place")."""

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            payload = {
                "message": record.getMessage(),
                "level": record.levelname,
                "logger": record.name,
            }
            if hasattr(record, "phase"):
                payload["phase"] = record.phase
            if hasattr(record, "duration_ms"):
                payload["duration_ms"] = record.duration_ms
            return json.dumps(payload)

    captured: list[str] = []

    class CapturingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(self.format(record))

    logger = logging.getLogger(_LOGGER_NAME)
    handler = CapturingHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        with _timed_phase("json_formatted_phase"):
            pass
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    assert len(captured) == 1
    payload = json.loads(captured[0])  # must be valid JSON
    assert payload["phase"] == "json_formatted_phase"
    assert isinstance(payload["duration_ms"], float)
    assert payload["duration_ms"] >= 0
    assert payload["level"] == "INFO"
    assert payload["logger"] == _LOGGER_NAME
    assert "cold_start_phase" in payload["message"]
