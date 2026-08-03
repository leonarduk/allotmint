import json
import logging
import logging.config
import sys
from datetime import datetime
from pathlib import Path

import pytest

import backend.logging_setup as logging_setup
from backend.logging_setup import JSONFormatter, sanitise_log_value

_LOGGING_INI = Path(__file__).resolve().parents[2] / "backend" / "logging.ini"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("hello", "hello"),
        ("ticker\nnewline", "tickernewline"),
        ("ticker\rreturn", "tickerreturn"),
        ("multi\r\nline", "multiline"),
        (123, "123"),
        (None, "None"),
        ("safe value", "safe value"),
        ("\n", ""),
        ("\r\n", ""),
        (["AAPL", "ticker\ninjection"], "['AAPL', 'ticker\\ninjection']"),
    ],
)
def test_sanitise_log_value(value, expected):
    assert sanitise_log_value(value) == expected


def _make_record(**kwargs):
    defaults = dict(
        name="my.logger",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    defaults.update(kwargs)
    return logging.LogRecord(**defaults)


def test_json_formatter_emits_valid_json_with_expected_fields():
    formatter = JSONFormatter()
    record = _make_record()

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "hello world"
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "my.logger"
    assert "timestamp" in payload
    assert "levelname" not in payload


def test_json_formatter_timestamp_is_iso8601():
    formatter = JSONFormatter()
    record = _make_record()

    payload = json.loads(formatter.format(record))

    # datetime.fromisoformat round-trips a valid ISO 8601 timestamp.
    datetime.fromisoformat(payload["timestamp"])


def test_json_formatter_output_stays_parseable_with_exc_info():
    """A logged exception's multi-line traceback must not break JSON parsing.

    json.dumps escapes embedded newlines within the exc_info string value,
    so the overall record still round-trips as a single, valid JSON object.
    """
    formatter = JSONFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = _make_record(msg="failed", args=None, exc_info=sys.exc_info())

    output = formatter.format(record)

    assert "\n" not in output
    payload = json.loads(output)
    assert payload["message"] == "failed"
    assert "ValueError: boom" in payload["exc_info"]


def test_json_switch_preserves_console_handler_filters(monkeypatch):
    """The JSON switch must only replace the formatter, never the handler
    object or its filters -- whatever filters logging.ini (or anything else)
    attached to the console handler survive the switch unchanged (issue
    #4681 constraint: "RedactTokenFilter must still apply to the JSON
    handler").

    Note: ``logging.config.fileConfig``'s classic INI format does not
    actually wire up a handler's ``filters=`` entry at all (that's a
    dictConfig-only feature) -- a pre-existing gap in this repo that predates
    and is unrelated to this change, and applies equally to the plain-text
    ``consoleHandler``. RedactTokenFilter's real effect today comes from the
    ``logging.getLogger().addFilter(...)`` call in
    ``backend/utils/telegram_utils.py``, attached directly to the root
    Logger object rather than any handler.
    """
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level
    root_logger.handlers = []
    monkeypatch.setattr(logging_setup.config, "log_format", "json")

    try:
        # fileConfig applies logging.ini's `[logger_root] level=INFO`, which
        # would otherwise leak into every later test's caplog capture if not
        # restored below.
        logging.config.fileConfig(_LOGGING_INI, disable_existing_loggers=False)

        console_handlers = [
            h for h in root_logger.handlers if type(h) is logging.StreamHandler and h.stream is sys.stdout
        ]
        assert console_handlers, "expected a stdout console handler wired from logging.ini"
        console_handler = console_handlers[0]
        filters_before = list(console_handler.filters)

        logging_setup.apply_log_format()

        assert isinstance(console_handler.formatter, JSONFormatter)
        assert console_handler.filters == filters_before
    finally:
        root_logger.handlers = original_handlers
        root_logger.setLevel(original_level)
