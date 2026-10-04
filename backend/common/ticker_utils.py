"""Ticker normalisation helpers used across offline/demo components."""

from __future__ import annotations

import os

DEFAULT_OFFLINE_TICKER = "PFE"
_FORCE_DEMO = os.getenv("TESTING") not in {None, "", "0", "false", "False"}

# The London Stock Exchange pads two-letter EPICs with a trailing dot
# (``BP.``, ``AV.``, ``SN.``) and brokers such as Hargreaves Lansdown export
# them that way.  A trailing dot on a 1-2 character symbol therefore means
# "LSE"; on a longer symbol it is malformed input, not a padded EPIC.
LSE_EXCHANGE = "L"
_PADDED_EPIC_MAX_LEN = 2


def split_ticker(ticker: str | None, exchange: str | None = None) -> tuple[str, str | None]:
    """Split ``ticker`` into ``(symbol, exchange)`` without ever returning ``""``.

    ``"BP.L"`` -> ``("BP", "L")``; ``"BP."`` -> ``("BP", "L")`` (padded LSE
    EPIC); ``"BP"`` with ``exchange="L"`` -> ``("BP", "L")``; ``"BP"`` ->
    ``("BP", None)``.  An explicit suffix on ``ticker`` wins over ``exchange``.

    Only 1-2 character symbols are padded EPICs: a bare trailing dot on a
    longer symbol (``"CASH."``, ``"FOO."``) is malformed and returns
    ``(symbol, None)`` -- no exchange, even if ``exchange`` is given.
    """
    raw = (ticker or "").strip().upper()
    symbol, dot, suffix = raw.partition(".")
    if not symbol:
        # "." / ".L" name no instrument; never pair an exchange with "".
        return "", None
    if suffix:
        return symbol, suffix
    if dot:
        return symbol, LSE_EXCHANGE if len(symbol) <= _PADDED_EPIC_MAX_LEN else None
    fallback = (exchange or "").strip().upper()
    return symbol, fallback or None


def canonical_ticker(ticker: str | None, exchange: str | None = None) -> str:
    """Return the single canonical ``SYMBOL.EXCHANGE`` key for ``ticker``.

    ``"BP."``, ``"bp.l"`` and ``("BP", "L")`` all become ``"BP.L"`` so prices,
    cache files and transaction pools share one key.  A bare symbol with no
    known exchange is returned bare; an empty exchange is never emitted.
    """
    symbol, exch = split_ticker(ticker, exchange)
    if not symbol:
        return ""
    return f"{symbol}.{exch}" if exch else symbol


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
