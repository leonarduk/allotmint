"""Central logging configuration utilities.

This module provides :func:`setup_logging` which configures the root logger
using the path specified in :mod:`backend.config`. It is safe to call multiple
 times; if logging is already configured the function does nothing.
"""

from __future__ import annotations

import logging
import logging.config
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from pythonjsonlogger.json import JsonFormatter

from backend.config import config


def sanitise_log_value(value: object) -> str:
    """Return a single-line string safe for plain-text logs.

    Strips ``\\r`` and ``\\n`` so an attacker cannot inject fake log lines
    via CWE-117 (log injection).
    """
    return str(value).replace("\r", "").replace("\n", "")


class JSONFormatter(JsonFormatter):
    """JSON formatter emitting ``timestamp``, ``level``, ``logger`` and ``message`` fields."""

    def add_fields(
        self,
        log_record: Dict[str, Any],
        record: logging.LogRecord,
        message_dict: Dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["level"] = log_record.pop("levelname", record.levelname)
        log_record["logger"] = log_record.pop("name", record.name)
        log_record["timestamp"] = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()


def _switch_console_handler_to_json(root_logger: logging.Logger) -> None:
    """Switch the console handler's formatter to JSON output.

    ``consoleHandler`` is a single instance shared by the root and uvicorn
    loggers (``fileConfig`` builds one handler per ini key and reuses it
    across every logger section that references it), so mutating its
    formatter here switches every logger to JSON at once.
    """
    formatter = JSONFormatter("%(levelname)s %(name)s %(message)s")
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setFormatter(formatter)


def setup_logging() -> None:
    """Configure application logging from configuration file.

    If the root logger already has handlers -- e.g. because uvicorn configured
    logging itself via ``--log-config`` before importing the app -- the
    ``fileConfig`` step is skipped to avoid overriding that configuration.
    The ``LOG_FORMAT=json`` switch still applies in that case, since it acts
    on whichever console handler is already installed.
    """
    root_logger = logging.getLogger()

    if not root_logger.handlers:
        log_config = config.log_config
        if log_config:
            base = config.repo_root or Path.cwd()
            config_path = Path(log_config)
            if not config_path.is_absolute():
                config_path = base / config_path

            if config_path.exists():
                try:
                    (base / "logs").mkdir(parents=True, exist_ok=True)
                except OSError:
                    # Best-effort: some deployment targets (e.g. a read-only
                    # filesystem) can't create it, and logging.ini's fileHandler
                    # will simply fail to open below if it truly needs the dir.
                    pass
                logging.config.fileConfig(config_path, disable_existing_loggers=False)

    if config.log_format == "json":
        _switch_console_handler_to_json(root_logger)
