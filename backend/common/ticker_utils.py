"""Ticker normalisation helpers used across offline/demo components."""

from __future__ import annotations

import os

DEFAULT_OFFLINE_TICKER = "PFE"
_FORCE_DEMO = os.getenv("TESTING") not in {None, "", "0", "false", "False"}


def canonical_cache_ticker(
    ticker: str,
    *,
    offline_mode: bool,
    fallback: str | None,
) -> str:
    """Return the symbol used for caching fundamentals data."""

    canonical = (ticker or "").upper()
    if not canonical:
        canonical = DEFAULT_OFFLINE_TICKER

    if offline_mode or _FORCE_DEMO:
        alt = (fallback or DEFAULT_OFFLINE_TICKER).strip()
        if alt:
            canonical = alt.upper()

    return canonical


def normalise_filter_ticker(
    ticker: str | None,
    *,
    offline_mode: bool,
    fallback: str | None,
) -> str | None:
    """Normalise ticker filters for demo/offline operation."""

    if ticker is None:
        return None

    canonical = ticker.upper()
    if offline_mode or _FORCE_DEMO:
        alt = (fallback or DEFAULT_OFFLINE_TICKER).strip()
        if alt:
            canonical = alt.upper()

    return canonical
