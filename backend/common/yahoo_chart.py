"""Latest-quote fields from Yahoo's chart endpoint instead of ``.info``.

``yfinance``'s ``Ticker.info`` calls Yahoo's ``quoteSummary`` endpoint, which
needs a cookie/crumb handshake. Yahoo increasingly rejects that handshake
(``401 Invalid Crumb``) or the endpoint itself (``401 User is unable to access
this feature``), so price lookups built on ``.info`` fail even when the
symbol is fine. The ``v8/finance/chart`` endpoint behind ``Ticker.history``
does not need a crumb, and its metadata carries the regular-market fields
quote and index views need.

``chart_quote`` returns those fields under the same keys ``.info`` used, so
callers can swap the source without remapping.
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, Mapping, Optional

# (marketState, currentTradingPeriod key), checked in this order.
_SESSIONS = (("PRE", "pre"), ("REGULAR", "regular"), ("POST", "post"))


def _to_epoch(value: Any) -> Optional[float]:
    """Return epoch seconds for an int/float or a pandas/datetime timestamp."""

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    to_ts = getattr(value, "timestamp", None)
    if callable(to_ts):
        try:
            return float(to_ts())
        except (TypeError, ValueError, OverflowError):
            return None
    return None


def market_state(metadata: Mapping[str, Any], now: Optional[float] = None) -> Optional[str]:
    """Derive Yahoo's ``marketState`` from the chart's ``currentTradingPeriod``.

    Returns ``PRE``/``REGULAR``/``POST`` while inside that session window,
    ``CLOSED`` otherwise, or ``None`` when the metadata has no trading periods.
    """

    periods = metadata.get("currentTradingPeriod")
    if not isinstance(periods, Mapping):
        return None
    current = time.time() if now is None else now
    for state, key in _SESSIONS:
        window = periods.get(key)
        if not isinstance(window, Mapping):
            continue
        start, end = _to_epoch(window.get("start")), _to_epoch(window.get("end"))
        if start is not None and end is not None and start <= current < end:
            return state
    return "CLOSED"


def _price_or_none(value: Any) -> Optional[float]:
    """Return ``value`` as a price, or ``None`` when Yahoo had no figure for it.

    Yahoo fills price fields it has no data for (an index's open/high/low,
    a weekend bar) with a literal ``0`` or ``NaN`` rather than omitting them.
    No instrument we quote trades at exactly zero, so passing those through
    renders "we don't know" as a confident ``0.00`` (#7819).
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value == 0 or not math.isfinite(value):
        return None
    return float(value)


def _last_row_value(history: Any, column: str) -> Optional[float]:
    """Return the last non-null, non-zero ``column`` price of a history frame, if any."""

    try:
        series = history[column].dropna()
    except (KeyError, TypeError, AttributeError):
        return None
    series = series[series != 0]
    if series.empty:
        return None
    return float(series.iloc[-1])


def _change_percent(price: Any, previous_close: Any) -> Optional[float]:
    if not isinstance(price, (int, float)) or not isinstance(previous_close, (int, float)):
        return None
    if previous_close == 0:
        return None
    return (float(price) - float(previous_close)) / float(previous_close) * 100.0


def chart_quote(ticker: Any) -> Dict[str, Any]:
    """Return ``.info``-style latest-quote fields for a ``yfinance.Ticker``.

    Makes one ``range=1d`` chart request. For that range Yahoo reports the
    prior session's close as ``chartPreviousClose``, which is the base
    ``regularMarketChangePercent`` is computed from. Network errors propagate
    so callers keep their existing per-symbol error handling.
    """

    history = ticker.history(period="1d", interval="1d", auto_adjust=False)
    metadata: Mapping[str, Any] = ticker.get_history_metadata() or {}

    price = _price_or_none(metadata.get("regularMarketPrice"))
    if price is None:
        price = _last_row_value(history, "Close")
    previous_close = _price_or_none(metadata.get("chartPreviousClose"))
    if previous_close is None:
        previous_close = _price_or_none(metadata.get("previousClose"))
    market_time = _to_epoch(metadata.get("regularMarketTime"))

    return {
        "regularMarketPrice": price,
        "regularMarketPreviousClose": previous_close,
        "regularMarketChangePercent": _change_percent(price, previous_close),
        "regularMarketOpen": _last_row_value(history, "Open"),
        "regularMarketDayHigh": _price_or_none(metadata.get("regularMarketDayHigh")),
        "regularMarketDayLow": _price_or_none(metadata.get("regularMarketDayLow")),
        "regularMarketVolume": metadata.get("regularMarketVolume"),
        "regularMarketTime": int(market_time) if market_time is not None else None,
        "exchangeTimezoneName": metadata.get("exchangeTimezoneName"),
        "marketState": market_state(metadata),
        "longName": metadata.get("longName"),
        "shortName": metadata.get("shortName"),
        "currency": metadata.get("currency"),
        "quoteType": metadata.get("instrumentType"),
    }
