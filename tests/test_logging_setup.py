import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import backend.logging_setup as logging_setup


def test_setup_logging_noop_when_root_logger_has_handlers(monkeypatch):
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers = [logging.NullHandler()]

    file_config_mock = MagicMock()
    monkeypatch.setattr(logging.config, "fileConfig", file_config_mock)
    monkeypatch.setattr(logging_setup.config, "log_config", "logging.ini")

    try:
        logging_setup.setup_logging()
        file_config_mock.assert_not_called()
    finally:
        root_logger.handlers = original_handlers


def test_setup_logging_relative_path(monkeypatch):
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers = []

    monkeypatch.setattr(logging_setup.config, "log_config", "logging.ini")
    monkeypatch.setattr(logging_setup.config, "repo_root", Path("/repo"))

    file_config_mock = MagicMock()
    monkeypatch.setattr(logging.config, "fileConfig", file_config_mock)
    monkeypatch.setattr(Path, "exists", lambda self: True)

    try:
        logging_setup.setup_logging()
        file_config_mock.assert_called_once_with(Path("/repo/logging.ini"), disable_existing_loggers=False)
    finally:
        root_logger.handlers = original_handlers


def test_json_formatter_emits_required_fields():
    formatter = logging_setup.JSONFormatter("%(levelname)s %(name)s %(message)s")
    record = logging.LogRecord(
        name="my.logger",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "WARNING"
    assert payload["logger"] == "my.logger"
    assert payload["message"] == "hello world"
    assert "levelname" not in payload
    assert "name" not in payload
    # timestamp must be ISO 8601 parseable
    from datetime import datetime

    datetime.fromisoformat(payload["timestamp"])


def test_switch_console_handler_to_json_mutates_shared_handler():
    root_logger = logging.getLogger("test.json.root")
    other_logger = logging.getLogger("test.json.uvicorn")
    shared_handler = logging.StreamHandler()
    shared_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.handlers = [shared_handler]
    other_logger.handlers = [shared_handler]

    logging_setup._switch_console_handler_to_json(root_logger)

    assert isinstance(root_logger.handlers[0].formatter, logging_setup.JSONFormatter)
    # Same handler instance is shared, so the other logger sees the switch too.
    assert other_logger.handlers[0] is root_logger.handlers[0]
    assert isinstance(other_logger.handlers[0].formatter, logging_setup.JSONFormatter)


def test_switch_console_handler_to_json_covers_stream_handler_subclasses():
    """A StreamHandler subclass (e.g. one uvicorn or another library installs)
    must still be switched -- an exact `type(handler) is StreamHandler` check
    would silently skip it."""

    class CustomStreamHandler(logging.StreamHandler):
        pass

    root_logger = logging.getLogger("test.json.subclass")
    custom_handler = CustomStreamHandler()
    root_logger.handlers = [custom_handler]

    logging_setup._switch_console_handler_to_json(root_logger)

    assert isinstance(custom_handler.formatter, logging_setup.JSONFormatter)


def test_switch_console_handler_to_json_leaves_file_handler_untouched(tmp_path):
    """FileHandler is a StreamHandler subclass; it must not be switched to JSON."""
    root_logger = logging.getLogger("test.json.filehandler")
    plain_formatter = logging.Formatter("%(message)s")
    file_handler = logging.FileHandler(tmp_path / "test.log")
    file_handler.setFormatter(plain_formatter)
    root_logger.handlers = [file_handler]

    try:
        logging_setup._switch_console_handler_to_json(root_logger)
        assert file_handler.formatter is plain_formatter
    finally:
        file_handler.close()


def test_switch_console_handler_to_json_preserves_existing_filters():
    """RedactTokenFilter (attached via logging.ini's filters=redactToken) must
    still apply after the formatter is swapped to JSON."""
    root_logger = logging.getLogger("test.json.filters")
    handler = logging.StreamHandler()
    marker_filter = logging.Filter(name="redactToken")
    handler.addFilter(marker_filter)
    root_logger.handlers = [handler]

    logging_setup._switch_console_handler_to_json(root_logger)

    assert marker_filter in root_logger.handlers[0].filters


def test_setup_logging_switches_to_json_when_configured(monkeypatch):
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers = []

    monkeypatch.setattr(logging_setup.config, "log_config", "logging.ini")
    monkeypatch.setattr(logging_setup.config, "log_format", "json")
    monkeypatch.setattr(Path, "exists", lambda self: True)

    stream_handler = logging.StreamHandler()

    def fake_file_config(*args, **kwargs):
        root_logger.handlers = [stream_handler]

    monkeypatch.setattr(logging.config, "fileConfig", fake_file_config)

    try:
        logging_setup.setup_logging()
        assert isinstance(stream_handler.formatter, logging_setup.JSONFormatter)
    finally:
        root_logger.handlers = original_handlers


def test_setup_logging_leaves_plain_text_formatter_when_log_format_unset(monkeypatch):
    """LOG_FORMAT unset (or anything other than "json") must not touch the
    formatter fileConfig installed -- today's plain-text-only behaviour."""
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers = []

    monkeypatch.setattr(logging_setup.config, "log_config", "logging.ini")
    monkeypatch.setattr(logging_setup.config, "log_format", None)
    monkeypatch.setattr(Path, "exists", lambda self: True)

    stream_handler = logging.StreamHandler()
    plain_formatter = logging.Formatter("%(message)s")
    stream_handler.setFormatter(plain_formatter)

    def fake_file_config(*args, **kwargs):
        root_logger.handlers = [stream_handler]

    monkeypatch.setattr(logging.config, "fileConfig", fake_file_config)

    try:
        logging_setup.setup_logging()
        assert stream_handler.formatter is plain_formatter
    finally:
        root_logger.handlers = original_handlers


def test_attach_redact_token_filter_adds_filter_to_each_handler_once():
    """fileConfig has no support for the ini's ``filters=`` handler directive,
    so ``setup_logging`` must attach RedactTokenFilter itself; calling it
    twice must not stack duplicate filter instances on the same handler."""
    from backend.utils.telegram_utils import RedactTokenFilter

    root_logger = logging.getLogger("test.redact_filter.root")
    handler_a = logging.StreamHandler()
    handler_b = logging.StreamHandler()
    root_logger.handlers = [handler_a, handler_b]

    logging_setup._attach_redact_token_filter(root_logger)
    logging_setup._attach_redact_token_filter(root_logger)

    for handler in (handler_a, handler_b):
        redact_filters = [f for f in handler.filters if isinstance(f, RedactTokenFilter)]
        assert len(redact_filters) == 1


def test_setup_logging_leaves_plain_text_formatter_when_log_format_is_non_json_value(monkeypatch):
    """LOG_FORMAT set to an explicit non-"json" value (e.g. "text") must not
    switch the formatter either -- only the exact string "json" triggers the
    switch (#5956)."""
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers = []

    monkeypatch.setattr(logging_setup.config, "log_config", "logging.ini")
    monkeypatch.setattr(logging_setup.config, "log_format", "text")
    monkeypatch.setattr(Path, "exists", lambda self: True)

    stream_handler = logging.StreamHandler()
    plain_formatter = logging.Formatter("%(message)s")
    stream_handler.setFormatter(plain_formatter)

    def fake_file_config(*args, **kwargs):
        root_logger.handlers = [stream_handler]

    monkeypatch.setattr(logging.config, "fileConfig", fake_file_config)

    try:
        logging_setup.setup_logging()
        assert stream_handler.formatter is plain_formatter
    finally:
        root_logger.handlers = original_handlers


def test_setup_logging_switches_to_json_when_uvicorn_preconfigured_logging(monkeypatch):
    """When uvicorn's own --log-config already populated root_logger.handlers
    (its Config.configure_logging() runs before the app is imported), fileConfig
    must be skipped but the JSON switch must still apply to the handler uvicorn
    installed (issue #4681 follow-up: setup_logging() previously wasn't wired
    into any real entrypoint, so this path never ran in production)."""
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]

    uvicorn_installed_handler = logging.StreamHandler()
    root_logger.handlers = [uvicorn_installed_handler]

    monkeypatch.setattr(logging_setup.config, "log_config", "logging.ini")
    monkeypatch.setattr(logging_setup.config, "log_format", "json")

    file_config_mock = MagicMock()
    monkeypatch.setattr(logging.config, "fileConfig", file_config_mock)

    try:
        logging_setup.setup_logging()
        file_config_mock.assert_not_called()
        assert isinstance(uvicorn_installed_handler.formatter, logging_setup.JSONFormatter)
    finally:
        root_logger.handlers = original_handlers
