"""Central logging configuration utilities.

This module provides :func:`setup_logging` which configures the root logger
using the path specified in :mod:`backend.config`. It is safe to call multiple
 times; if logging is already configured the function does nothing.
"""

from __future__ import annotations

import logging
import logging.config
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from pythonjsonlogger.json import JsonFormatter

from backend.config import config

JSON_LOG_FORMAT = "json"

_CONSOLE_LOGGER_NAMES = (None, "uvicorn", "uvicorn.error", "uvicorn.access")


def sanitise_log_value(value: object) -> str:
    """Return a single-line string safe for plain-text logs.

    Strips ``\\r`` and ``\\n`` so an attacker cannot inject fake log lines
    via CWE-117 (log injection).
    """
    return str(value).replace("\r", "").replace("\n", "")


class JSONFormatter(JsonFormatter):
    """JSON log formatter with consistent field names.

    Renames ``levelname`` to ``level`` and emits an ISO 8601 ``timestamp``,
    so logs can be ingested by structured log aggregators (CloudWatch Logs
    Insights, Datadog, etc.) without regex parsing.
    """

    def add_fields(
        self,
        log_record: Dict[str, Any],
        record: logging.LogRecord,
        message_dict: Dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        log_record["level"] = log_record.pop("levelname", record.levelname)
        log_record.setdefault("logger", record.name)
        log_record.setdefault("message", record.getMessage())


def _switch_console_handlers_to_json() -> None:
    """Swap plain-text console handlers to JSON output.

    ``logging.config.fileConfig`` wires logger-to-handler associations
    statically from ``logging.ini``, so the exclusive plain-text/JSON switch
    for ``LOG_FORMAT=json`` has to happen here in code, after the ini has
    already been applied, rather than in the ini file itself.
    """
    formatter = JSONFormatter()
    seen_handler_ids: set[int] = set()
    for logger_name in _CONSOLE_LOGGER_NAMES:
        for handler in logging.getLogger(logger_name).handlers:
            is_console_stream_handler = type(handler) is logging.StreamHandler and handler.stream is sys.stdout
            if is_console_stream_handler and id(handler) not in seen_handler_ids:
                handler.setFormatter(formatter)
                seen_handler_ids.add(id(handler))


def setup_logging() -> None:
    """Configure application logging from configuration file.

    If the root logger already has handlers, the function returns immediately
    to avoid overriding existing logging configuration (e.g. when uvicorn
    configures logging via ``--log-config``).
    """
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    log_config = config.log_config
    if not log_config:
        return

    config_path = Path(log_config)
    if not config_path.is_absolute():
        base = config.repo_root or Path.cwd()
        config_path = base / config_path

    if config_path.exists():
        logging.config.fileConfig(config_path, disable_existing_loggers=False)
        if config.log_format == JSON_LOG_FORMAT:
            _switch_console_handlers_to_json()
