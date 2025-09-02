"""Utilities for loading instrument metadata."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

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
            data = json.load(f)
        for field in ("asset_class", "industry", "region"):
            data.setdefault(field, None)
        return data
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        logger.warning("Invalid instrument JSON %s: %s", path, exc)
        return {}
    except Exception:
        logger.exception("Unexpected error loading instrument metadata for %s", path)
        raise


def save_instrument_meta(ticker: str, meta: Dict[str, Any]) -> None:
    """Write ``meta`` for ``ticker`` back to disk.

    ``meta`` must already include ``ticker`` and any desired optional fields.
    Missing directories are created automatically.
    """

    path = _instrument_path(ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def list_instruments() -> List[Dict[str, Any]]:
    """Return metadata for every instrument found under ``data/instruments``."""

    instruments: List[Dict[str, Any]] = []
    for p in _INSTRUMENTS_DIR.rglob("*.json"):
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for field in ("asset_class", "industry", "region"):
                data.setdefault(field, None)
            instruments.append(data)
        except Exception:
            logger.warning("Failed to load instrument metadata for %s", p)
    return instruments
