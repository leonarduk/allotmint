"""Split a non-sterling instrument's GBP price return into local and FX parts (#9776).

For an instrument quoted in ``C != GBP`` between its first and last stored
close in a window::

    local = P1 / P0 - 1        native closes (``Close``, not ``Close_gbp``)
    fx    = FX1 / FX0 - 1      GBP per unit of ``C`` from the stored FX history
    cross = local * fx
    gbp   = local + fx + cross = (1 + local) * (1 + fx) - 1

The cross term is reported on its own line, so the three parts sum to the GBP
return exactly. It is a price return: no dividends.

Cache-only (#8028): closes come from the stored timeseries and rates from the
stored FX history through :func:`portfolio_utils._gbp_rates`, the bounded
gap-fill rule the GBP value series uses (#9671, #9759). If either endpoint has
no rate within that window there is no split. It is never computed from an
approximate fallback constant (#9664).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from backend.common import portfolio_utils as pu
from backend.timeseries.cache import cache_only, load_meta_timeseries_range
from backend.utils.timeseries_helpers import get_scaling_override

PRICE_RETURN = "price"

# ``reason`` values. ``applicable`` is False only for the first two: the
# frontend hides the panel for those rather than showing a 0% FX component.
REASON_STERLING = "sterling_instrument"
REASON_UNKNOWN_CURRENCY = "unknown_currency"
REASON_CURRENCY_MISMATCH = "currency_mismatch"
REASON_NO_PRICE_HISTORY = "insufficient_price_history"
REASON_MISSING_FX = "missing_fx_rate"


def _result(ticker: str, currency: str, *, applicable: bool, reason: str | None = None) -> dict[str, Any]:
    """A result with every component ``None``; the caller fills in what it measured."""
    return {
        "ticker": ticker,
        "currency": currency,
        "applicable": applicable,
        "basis": PRICE_RETURN,
        "reason": reason,
        "start": None,
        "end": None,
        "start_rate": None,
        "end_rate": None,
        "local_return": None,
        "fx_return": None,
        "cross_term": None,
        "gbp_return": None,
    }


def _quote_currency(ticker: str, exchange: str) -> tuple[str, str]:
    """``(currency to report, currency the stored ``Close_gbp`` is converted from)``.

    The first is the phase 1-2 resolver (:func:`portfolio_utils.holding_quote_currency`,
    GBX folded into GBP). The second is the one ``_closes_in_gbp`` and the
    timeseries loader convert with. They should agree. When they don't, the
    split would use a different rate from the page's GBP closes, so the
    caller reports the mismatch instead of a split.
    """
    quote = pu.holding_quote_currency({"ticker": f"{ticker}.{exchange}", "exchange": exchange})
    norm = pu._holding_currency(ticker, exchange)
    conversion = "GBP" if norm.is_pence else norm.canonical
    return quote, conversion


def _native_endpoints(ticker: str, exchange: str, start: date, end: date) -> pd.Series:
    """The first and last stored native closes in ``start..end`` (scaled), indexed by date.

    Applies the instrument's scaling override as ``_closes_in_gbp`` does. A
    constant scale cancels out of the return, but it keeps the closes
    comparable with the page's. Fewer than two dates gives a shorter series.
    """
    with cache_only():
        df = load_meta_timeseries_range(ticker, exchange, start_date=start, end_date=end)
    if df.empty or "Date" not in df.columns or "Close" not in df.columns:
        return pd.Series(dtype=float)
    closes = pd.to_numeric(df.set_index(pd.to_datetime(df["Date"]))["Close"], errors="coerce").dropna()
    closes = closes[closes > 0].sort_index()
    closes = closes[~closes.index.duplicated(keep="last")]
    scale = get_scaling_override(ticker, exchange, None) or 1.0
    return pd.concat([closes.head(1), closes.tail(1)]) * scale if len(closes) >= 2 else closes.iloc[:0]


def local_fx_return_split(ticker: str, exchange: str, start: date, end: date) -> dict[str, Any]:
    """Local, FX and cross-term parts of ``ticker.exchange``'s GBP price return over ``start..end``.

    ``start``/``end`` in the result are the dates of the first and last stored
    closes in the window, which are the dates the return is measured between.
    ``start_rate``/``end_rate`` are GBP per unit of the quote currency on those
    dates. See the module docstring for the formulae and the ``reason`` values.
    """
    full = f"{ticker}.{exchange}".upper()
    quote, conversion = _quote_currency(ticker, exchange)
    if quote == "GBP":
        return _result(full, quote, applicable=False, reason=REASON_STERLING)
    if quote == pu.UNKNOWN_CURRENCY_LABEL:
        return _result(full, quote, applicable=False, reason=REASON_UNKNOWN_CURRENCY)
    if quote != conversion:
        return _result(full, quote, applicable=True, reason=REASON_CURRENCY_MISMATCH)

    closes = _native_endpoints(ticker, exchange, start, end)
    if len(closes) < 2:
        return _result(full, quote, applicable=True, reason=REASON_NO_PRICE_HISTORY)

    rates = pu._gbp_rates(quote, closes.index)
    result = _result(full, quote, applicable=True)
    result["start"], result["end"] = (day.date().isoformat() for day in closes.index)
    start_rate, end_rate = (None if pd.isna(rate) else float(rate) for rate in rates)
    result["start_rate"], result["end_rate"] = start_rate, end_rate
    if start_rate is None or end_rate is None or start_rate <= 0:
        result["reason"] = REASON_MISSING_FX
        return result

    local = float(closes.iloc[1] / closes.iloc[0] - 1)
    fx = end_rate / start_rate - 1
    result.update(local_return=local, fx_return=fx, cross_term=local * fx, gbp_return=(1 + local) * (1 + fx) - 1)
    return result
