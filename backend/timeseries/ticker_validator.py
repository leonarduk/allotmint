from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from backend.common.instruments import get_instrument_meta

logger = logging.getLogger("ticker_validator")

# File to record skipped tickers for auditing
SKIPPED_TICKERS_FILE = Path(__file__).resolve().parents[2] / "data" / "skipped_tickers.log"


@lru_cache(maxsize=4096)
def is_valid_ticker(ticker: str, exchange: str) -> bool:
    """Return True if ticker has known instrument metadata."""
    base = ticker.split(".")[0].upper()
    ex = exchange.upper()
    full = f"{base}.{ex}"
    meta = get_instrument_meta(full)
    return bool(meta)


def record_skipped_ticker(ticker: str, exchange: str, *, reason: str = "") -> None:
    """Append ticker to the skipped log for later auditing."""
    try:
        SKIPPED_TICKERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().isoformat()
        line = f"{ts},{ticker},{exchange},{reason}\n"
        with SKIPPED_TICKERS_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:
        logger.warning("Failed to record skipped ticker %s.%s: %s", ticker, exchange, exc)
