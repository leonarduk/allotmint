"""Effective trend-watch thresholds: ``config.trend_watch`` overlaid with the Bots page settings (#10476, #10477).

The same pattern as :func:`backend.agent.trading_agent.load_strategy_config`:
server config is the base, and only the public threshold fields saved for the
``trend-watch`` bot can override it.
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from backend.config import TrendWatchConfig, config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

BOT_ID = "trend-watch"


def load_base_trend_watch_config() -> TrendWatchConfig:
    """The thresholds from server config only."""

    return TrendWatchConfig(**asdict(config.trend_watch))


def load_trend_watch_config() -> TrendWatchConfig:
    """The thresholds a run uses: server config overlaid with the saved bot settings."""

    base = asdict(load_base_trend_watch_config())
    try:
        from backend.bots.settings import load_stored_settings

        stored = load_stored_settings(BOT_ID)
    except Exception as exc:
        logger.error("Failed to load saved trend-watch bot settings: %s", sanitise_log_value(exc))
        stored = {}
    base.update({key: value for key, value in stored.items() if key in base})
    return TrendWatchConfig(**base)
