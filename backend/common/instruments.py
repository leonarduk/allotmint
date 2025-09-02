"""Utilities for loading instrument metadata."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

_INSTRUMENTS_DIR = Path(__file__).resolve().parents[2] / "data" / "instruments"
_VALID_RE = re.compile(r"^[A-Z0-9-]+$")

logger = logging.getLogger(__name__)


def _validate_part(value: str) -> str:
    """Return ``value`` upper-cased if it matches ``_VALID_RE``."""

    value = value.upper()
    if not _VALID_RE.match(value):
        raise ValueError("invalid ticker or exchange")
    return value


def _instrument_path(ticker: str) -> Path:
    sym, exch = (ticker.split(".", 1) + [None])[:2]
    sym = _validate_part(sym)
    if exch is not None:
        exch = _validate_part(exch)
    if sym == "CASH":
        ccy = exch or "GBP"
        return _INSTRUMENTS_DIR / "Cash" / f"{ccy}.json"
    folder = exch if exch else "Unknown"
    return _INSTRUMENTS_DIR / folder / f"{sym}.json"


@lru_cache(maxsize=2048)
def get_instrument_meta(ticker: str) -> Dict[str, Any]:
    """Return metadata for ``ticker`` from disk.

    The data files live under ``data/instruments``; failures return an empty dict.
    """
    try:
        path = _instrument_path(ticker)
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        logger.warning("Invalid instrument JSON %s: %s", path, exc)
        return {}
    except ValueError:
        logger.warning("Invalid ticker format: %s", ticker)
        return {}
    except Exception:
        logger.exception("Unexpected error loading instrument metadata for %s", ticker)
        raise


def instrument_meta_path(ticker: str, exchange: str) -> Path:
    """Return the filesystem path for a ticker/exchange pair."""

    sym = _validate_part(ticker)
    exch = _validate_part(exchange)
    return _instrument_path(f"{sym}.{exch}")


def save_instrument_meta(ticker: str, exchange: str, data: Dict[str, Any]) -> Path:
    """Persist ``data`` for ``ticker`` on ``exchange`` and return the path."""

    if not isinstance(data, dict):
        raise TypeError("data must be a dict")
    path = instrument_meta_path(ticker, exchange)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
    except OSError as exc:  # pragma: no cover - filesystem errors are rare
        logger.exception("Failed to write instrument metadata %s", path)
        raise
    get_instrument_meta.cache_clear()
    return path


def delete_instrument_meta(ticker: str, exchange: str) -> None:
    """Delete the metadata file for ``ticker`` on ``exchange`` if present."""

    path = instrument_meta_path(ticker, exchange)
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except PermissionError:
        logger.warning("Permission denied deleting %s", path)
        return
    get_instrument_meta.cache_clear()
