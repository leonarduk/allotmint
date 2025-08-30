"""Central logging configuration utilities.

This module provides :func:`setup_logging` which configures the root logger
using the path specified in :mod:`backend.config`. It is safe to call multiple
 times; if logging is already configured the function does nothing.
"""
from __future__ import annotations

import logging
import logging.config
from pathlib import Path

from backend.config import config


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
