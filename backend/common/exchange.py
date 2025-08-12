from __future__ import annotations

"""Helpers for resolving ticker exchanges."""

from functools import lru_cache
from pathlib import Path

# Directory containing instrument metadata organised by exchange folders
_INSTRUMENTS_DIR = Path(__file__).resolve().parents[2] / "data" / "instruments"


@lru_cache(maxsize=2048)
def guess_exchange(ticker: str) -> str:
    """Return the exchange for ``ticker`` if known, defaulting to ``"L"``.

    The lookup checks the ``data/instruments`` tree for a matching JSON file.
    If ``ticker`` already contains an exchange suffix (``"SYM.EX"``) the
    explicit suffix is returned.  Unknown tickers fall back to ``"L"`` to retain
    previous behaviour.
    """
    if not ticker:
        return "L"

    sym, exch = (ticker.split(".", 1) + [None])[:2]
    if exch:  # already specified
        return exch.upper()

    sym = sym.upper()
    try:
        for p in _INSTRUMENTS_DIR.iterdir():
            if not p.is_dir() or p.name in {"Cash", "Unknown"}:
                continue
            if (p / f"{sym}.json").exists():
                return p.name
    except FileNotFoundError:
        pass

    return "L"
