"""Extra tickers the scheduled price refresh keeps fresh beyond holdings and triggers (#10624).

The list is optional JSON, ``{"tickers": ["SPY.N", "VWRL.L", ...]}`` (a bare list is
accepted too), read through the JSON storage abstraction:

* ``PRICE_REFRESH_EXTRA_URI`` when set (``file://``, ``s3://`` or ``ssm://``);
* otherwise ``file://<data_root>/price_refresh_extra.json``.

S3 is never inferred from ``DATA_BUCKET``: the refresh Lambda has a 10-minute timeout, so a
deployment only refreshes a large extra list when it opts in explicitly. A missing,
unreadable or malformed list means no extras; it never fails the refresh.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, List

from backend.common.storage import get_storage
from backend.common.ticker_utils import canonical_ticker
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

URI_ENV = "PRICE_REFRESH_EXTRA_URI"
FILENAME = "price_refresh_extra.json"


def _default_uri() -> str:
    explicit = os.getenv(URI_ENV)
    if explicit:
        return explicit
    root = Path(config.data_root) if config.data_root else Path(__file__).resolve().parents[2] / "data"
    return f"file://{root / FILENAME}"


def _ticker_list(data: Any) -> List[Any]:
    if isinstance(data, dict):
        data = data.get("tickers", [])
    return data if isinstance(data, list) else []


def extra_refresh_tickers() -> List[str]:
    """Canonical (``SYMBOL.EXCHANGE``), de-duplicated extra tickers in file order; ``[]`` when none can be read."""
    uri = _default_uri()
    try:
        data = get_storage(uri).load()
    except Exception as exc:  # an extras problem must never fail the price refresh
        logger.warning(
            "Could not read extra refresh tickers from %s: %s", sanitise_log_value(uri), sanitise_log_value(exc)
        )
        return []
    raw = _ticker_list(data)
    if data and not raw:
        logger.warning('Ignoring %s: expected {"tickers": [...]} or a list', sanitise_log_value(uri))
    tickers = (canonical_ticker(t) for t in raw if isinstance(t, str))
    return list(dict.fromkeys(t for t in tickers if t))
