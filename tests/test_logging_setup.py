import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import backend.logging_setup as logging_setup
from backend.logging_setup import JSONFormatter


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


def test_setup_logging_switches_console_to_json_when_log_format_json(monkeypatch):
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers = []

    monkeypatch.setattr(logging_setup.config, "log_config", "logging.ini")
    monkeypatch.setattr(logging_setup.config, "log_format", "json")
    monkeypatch.setattr(logging_setup.config, "repo_root", Path("/repo"))
    monkeypatch.setattr(Path, "exists", lambda self: True)

    console_handler = logging.StreamHandler(sys.stdout)

    def fake_file_config(*args, **kwargs):
        # fileConfig wires handlers onto the root logger from the ini file;
        # simulate that by attaching a plain-text console handler.
        root_logger.addHandler(console_handler)

    monkeypatch.setattr(logging.config, "fileConfig", fake_file_config)

    try:
        logging_setup.setup_logging()
        assert isinstance(console_handler.formatter, JSONFormatter)
    finally:
        root_logger.handlers = original_handlers


def test_switch_console_handlers_to_json_ignores_non_stdout_handlers():
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    stdout_handler = logging.StreamHandler(sys.stdout)
    other_handler = logging.StreamHandler(sys.stderr)
    root_logger.handlers = [stdout_handler, other_handler]

    try:
        logging_setup._switch_console_handlers_to_json()
        assert isinstance(stdout_handler.formatter, JSONFormatter)
        assert not isinstance(other_handler.formatter, JSONFormatter)
    finally:
        root_logger.handlers = original_handlers
