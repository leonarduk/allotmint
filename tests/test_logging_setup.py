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
