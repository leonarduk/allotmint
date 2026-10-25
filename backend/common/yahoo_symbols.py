"""Yahoo Finance spelling of app tickers that differ only in punctuation.

The app stores US share classes with a dot (``BRK.B``, ``BF.B``), but Yahoo
spells them with a dash (``BRK-B``, ``BF-B``) and returns no data for the
dotted form (#11081). Exchange suffixes are handled by the callers' suffix
maps; this module only rewrites the share-class separator.
"""

from __future__ import annotations

import re

# App exchange codes for US listings (their Yahoo suffix is empty).
US_EXCHANGES = frozenset({"N", "US", "NYSE", "NASDAQ"})

# An alphabetic root plus a single-letter class: ``BRK.B``. Excludes LSE
# symbols (``BP.L`` is never on a US exchange), multi-letter suffixes
# (``IWDA.AS``), numeric codes, index ``^`` and FX ``=X`` symbols.
_SHARE_CLASS = re.compile(r"^([A-Z]+)\.([A-Z])$")


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
