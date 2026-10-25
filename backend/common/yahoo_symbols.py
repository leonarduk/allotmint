"""Yahoo Finance spelling of app tickers.

Yahoo wants each exchange's suffix (``XDEV.L``, none for US listings) and
spells US share classes with a dash (``BRK-B``) where the app stores a dot
(``BRK.B``); it returns no data for the dotted form (#11081).
:func:`yahoo_symbol_for` applies both and is the one place callers get a
Yahoo symbol from (#11084).
"""

from __future__ import annotations

import re

# App exchange codes for US listings (their Yahoo suffix is empty).
US_EXCHANGES = frozenset({"N", "US", "NYSE", "NASDAQ"})

# An alphabetic root plus a single-letter class: ``BRK.B``. Excludes LSE
# symbols (``BP.L`` is never on a US exchange), multi-letter suffixes
# (``IWDA.AS``), numeric codes, index ``^`` and FX ``=X`` symbols.
_SHARE_CLASS = re.compile(r"^([A-Z]+)\.([A-Z])$")

# App exchange code -> Yahoo Finance ticker suffix.
_EXCHANGE_SUFFIXES = {
    "LSE": ".L",
    "L": ".L",
    "UK": ".L",
    "NASDAQ": "",
    "NYSE": "",
    "N": "",
    "US": "",
    "PARIS": ".PA",
    "XETRA": ".DE",
    "DE": ".DE",
    "TSX": ".TO",
    "TO": ".TO",
    "ASX": ".AX",
    "F": ".F",
    "MI": ".MI",
    "FX": "=X",
}


def get_yahoo_suffix(exchange: str) -> str:
    """Yahoo's suffix for app exchange code ``exchange``; ``ValueError`` if it has none."""
    suffix = _EXCHANGE_SUFFIXES.get(exchange.upper())
    if suffix is None:
        raise ValueError(f"Unsupported exchange: '{exchange}'")
    return suffix


def with_yahoo_suffix(ticker: str, exchange: str) -> str:
    """``ticker`` upper-cased with its exchange's Yahoo suffix, never duplicated.

    with_yahoo_suffix("XDEV", "L")   -> "XDEV.L"
    with_yahoo_suffix("XDEV.L", "L") -> "XDEV.L"
    with_yahoo_suffix("BRK.B", "N")  -> "BRK.B"
    """
    suffix = get_yahoo_suffix(exchange)
    ticker = ticker.upper()
    if ticker.endswith(suffix):  # already has ".L", ".DE", ...
        return ticker
    return ticker + suffix


def yahoo_share_class_symbol(symbol: str, exchange: str) -> str:
    """Return ``symbol`` with a US share-class dot replaced by Yahoo's dash.

    ``symbol`` is the app ticker without any exchange suffix; anything that is
    not a US-listed ``X.Y`` share class comes back unchanged.
        yahoo_share_class_symbol("BRK.B", "N")  -> "BRK-B"
        yahoo_share_class_symbol("BP.L", "L")   -> "BP.L"
        yahoo_share_class_symbol("AAPL", "US")  -> "AAPL"
    """
    if exchange.upper() not in US_EXCHANGES:
        return symbol
    match = _SHARE_CLASS.match(symbol.upper())
    if match is None:
        return symbol
    return f"{match.group(1)}-{match.group(2)}"


def yahoo_symbol_for(ticker: str, exchange: str) -> str:
    """The Yahoo Finance symbol for app ``ticker`` listed on ``exchange``.

    Adds the exchange suffix (never twice) and, for a US listing, swaps a
    share-class dot for Yahoo's dash. ``ValueError`` for an unknown exchange.
        yahoo_symbol_for("XDEV", "L")     -> "XDEV.L"
        yahoo_symbol_for("BRK.B", "US")   -> "BRK-B"
        yahoo_symbol_for("GBPUSD", "FX")  -> "GBPUSD=X"
    """
    return yahoo_share_class_symbol(with_yahoo_suffix(ticker, exchange), exchange)
