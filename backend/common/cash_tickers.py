"""Tell a cash-balance ticker (``CASH.GBP``) apart from a stock called ``CASH``.

Cash balances are held as ``CASH.<ccy>`` (legacy ``<ccy>.CASH``, or a bare
``CASH`` meaning GBP). ``CASH`` is also a real equity symbol, e.g. Pathward
Financial on Nasdaq (``CASH.N``), so the suffix decides: ``CASH`` is cash only
when the suffix is a currency code (#10516).

The currencies are an explicit allowlist rather than "any three letters",
because some exchange suffixes (``ASX``) are three letters too.
"""

from __future__ import annotations

CASH_SYMBOL = "CASH"

# ISO 4217 codes a cash balance may be held in. None of them is used as an
# exchange suffix in this repo (L, N, US, DE, TO, F, PARIS, ASX, ...).
CASH_CURRENCIES = frozenset(
    {
        "AUD",
        "CAD",
        "CHF",
        "CNY",
        "DKK",
        "EUR",
        "GBP",
        "HKD",
        "JPY",
        "NOK",
        "NZD",
        "SEK",
        "SGD",
        "USD",
        "ZAR",
    }
)


def is_cash_ticker(ticker: object) -> bool:
    """True for ``CASH``, ``CASH.<ccy>`` and legacy ``<ccy>.CASH`` tickers.

    ``CASH`` on a real exchange (``CASH.N``, ``CASH.US``) is an equity, not cash.
    """
    if not isinstance(ticker, str):
        return False
    symbol, _, suffix = ticker.strip().upper().partition(".")
    if symbol == CASH_SYMBOL:
        return not suffix or suffix in CASH_CURRENCIES
    return suffix == CASH_SYMBOL
