"""Utilities for loading instrument metadata."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

_INSTRUMENTS_DIR = Path(__file__).resolve().parents[2] / "data" / "instruments"

logger = logging.getLogger(__name__)


def _instrument_path(ticker: str) -> Path:
    sym, exch = (ticker.split(".", 1) + [None])[:2]
    sym = sym.upper()
    if sym == "CASH":
        ccy = (exch or "GBP").upper()
        return _INSTRUMENTS_DIR / "Cash" / f"{ccy}.json"
    folder = exch.upper() if exch else "Unknown"
    return _INSTRUMENTS_DIR / folder / f"{sym}.json"


@lru_cache(maxsize=2048)
def get_instrument_meta(ticker: str) -> Dict[str, Any]:
    """Return metadata for ``ticker`` from disk.

    The data files live under ``data/instruments``; failures return an empty dict.
    """
    path = _instrument_path(ticker)
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        logger.warning("Invalid instrument JSON %s: %s", path, exc)
        return {}
    except Exception:
        logger.exception("Unexpected error loading instrument metadata for %s", path)
        raise


def instrument_meta_path(ticker: str, exchange: str) -> Path:
    """Return the filesystem path for a ticker/exchange pair."""

    return _instrument_path(f"{ticker}.{exchange}")


def save_instrument_meta(ticker: str, exchange: str, data: Dict[str, Any]) -> Path:
    """Persist ``data`` for ``ticker`` on ``exchange`` and return the path."""

    path = instrument_meta_path(ticker, exchange)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    get_instrument_meta.cache_clear()
    return path


def delete_instrument_meta(ticker: str, exchange: str) -> None:
    """Delete the metadata file for ``ticker`` on ``exchange`` if present."""

    path = instrument_meta_path(ticker, exchange)
    try:
        path.unlink()
    except FileNotFoundError:
        return
    get_instrument_meta.cache_clear()
