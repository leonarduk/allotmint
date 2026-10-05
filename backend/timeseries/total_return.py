"""Total return from traded prices plus stored dividends (#9340).

Cached closes are the traded price (``auto_adjust=False``), so a series'
price return excludes income. Consumers that want total return combine the
closes with the dividends in ``corporate_actions`` instead of reading a
dividend-adjusted ``Close``::

    closes = df.set_index("Date")["Close"]
    tr = total_return_index(closes, load_dividends("VHYL", "L"))

Each dividend is reinvested at the close of its ex-date (or the next close
in the series when the ex-date itself is missing): on that day the holder's
growth factor is ``(close + dividend) / previous close``. Dividends must be
in the same units as the closes, which is how Yahoo reports them.
"""

from __future__ import annotations

import pandas as pd


def _clean_closes(closes: pd.Series) -> pd.Series:
    values = pd.to_numeric(closes, errors="coerce")
    values.index = pd.to_datetime(values.index).normalize()
    values = values[values.notna() & (values > 0)]
    values = values[~values.index.duplicated(keep="last")]
    return values.sort_index().astype(float)


def dividends_on_trading_days(closes: pd.Series, dividends: pd.Series | None) -> pd.Series:
    """Dividend per trading day of ``closes`` (0 where none); ex-dates snap to the next close.

    Dividends whose ex-date falls on or before the first close are dropped:
    the first close is already ex-dividend when the ex-date equals it, so a
    holder from that close is not entitled (only a holder from the previous,
    out-of-window close is). Those after the last close are dropped too.
    """
    closes = _clean_closes(closes)
    paid = pd.Series(0.0, index=closes.index)
    if dividends is None or dividends.empty or closes.empty:
        return paid
    divs = pd.to_numeric(dividends, errors="coerce").dropna()
    divs.index = pd.to_datetime(divs.index).normalize()
    positions = closes.index.searchsorted(divs.index, side="left")
    for pos, amount in zip(positions, divs.to_numpy()):
        if 0 < pos < len(closes):
            paid.iloc[int(pos)] += float(amount)
    return paid


def total_return_index(
    closes: pd.Series,
    dividends: pd.Series | None,
    *,
    base: float | None = None,
) -> pd.Series:
    """Price-plus-reinvested-dividends index over the dates of ``closes``.

    Starts at ``base`` (default: the first close, so the index reads in price
    units and equals the price series when no dividends are paid).
    """
    clean = _clean_closes(closes)
    if clean.empty:
        return clean
    paid = dividends_on_trading_days(clean, dividends)
    growth = (clean + paid) / clean.shift(1)
    growth.iloc[0] = 1.0
    start = float(clean.iloc[0]) if base is None else float(base)
    return (growth.cumprod() * start).rename("TotalReturn")


def total_return(closes: pd.Series, dividends: pd.Series | None) -> float | None:
    """Total return from the first to the last close, or ``None`` with fewer than two closes."""
    index = total_return_index(closes, dividends, base=1.0)
    if len(index) < 2:
        return None
    return float(index.iloc[-1] - 1.0)
