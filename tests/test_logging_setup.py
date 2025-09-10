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
