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

# ISO 4217 codes a cash balance may be held in, plus ``GBX`` for a pence
# account's cash (``CASH.GBX``). None of them is used as an exchange suffix in
# this repo (L, N, US, DE, TO, F, PARIS, ASX, ...).
CASH_CURRENCIES = frozenset(
    {
        "AUD",
        "CAD",
        "CHF",
        "CNY",
        "DKK",
        "EUR",
        "GBP",
        "GBX",
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


def is_cash_listing(symbol: object, exchange: object) -> bool:
    """:func:`is_cash_ticker` for a ticker already split into symbol and exchange.

    ``("CASH", "GBP")`` and ``("GBP", "CASH")`` are cash; ``("CASH", "N")`` is
    Pathward Financial. A symbol that still carries its own suffix, or has no
    exchange, is judged on the symbol alone.
    """
    if not isinstance(symbol, str):
        return False
    exch = exchange.strip() if isinstance(exchange, str) else ""
    if "." in symbol or not exch:
        return is_cash_ticker(symbol)
    return is_cash_ticker(f"{symbol.strip()}.{exch}")


def cash_ticker_currency(ticker: object) -> str | None:
    """``USD`` for ``CASH.USD``/legacy ``USD.CASH``; ``None`` for anything else.

    Only codes in :data:`CASH_CURRENCIES` count, so ``CASH.N`` or ``CASH.ASX``
    never yield an exchange suffix as a currency. A bare ``CASH`` names no
    currency, so callers apply their own default.
    """
    if not is_cash_ticker(ticker):
        return None
    symbol, _, suffix = str(ticker).strip().upper().partition(".")
    code = suffix if symbol == CASH_SYMBOL else symbol
    return code if code in CASH_CURRENCIES else None


def cash_price_key(ticker: object, symbol: str, exchange: str) -> tuple[str, str]:
    """Keep a cash holding on a cash ``(symbol, exchange)`` key after resolution.

    Resolving a bare ``CASH`` (or a holding whose stored ``exchange`` names a
    market) can yield ``("CASH", "L")`` or ``("CASH", "N")``, which
    :func:`is_cash_listing` rightly reads as a stock. The stored ``ticker`` is
    what says the holding is cash, so it maps to ``("CASH", <ccy>)`` (bare
    ``CASH`` is GBP). Any other key is returned unchanged.
    """
    if not is_cash_ticker(ticker) or is_cash_listing(symbol, exchange):
        return symbol, exchange
    return CASH_SYMBOL, cash_ticker_currency(ticker) or "GBP"
