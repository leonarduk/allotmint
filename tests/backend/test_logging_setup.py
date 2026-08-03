import json
import logging
import sys
from datetime import datetime

import pytest

from backend.logging_setup import JSONFormatter, sanitise_log_value


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
