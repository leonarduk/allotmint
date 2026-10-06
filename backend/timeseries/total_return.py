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

Consumers that measure performance (#9370) go through
:func:`total_return_closes` / :func:`total_return_frame`, which load the
dividends themselves and report the ``return_basis`` they could achieve.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Callable

import numpy as np
import pandas as pd

from backend.common.ticker_utils import split_ticker
from backend.logging_setup import sanitise_log_value
from backend.timeseries.corporate_actions import CONFIRMED_FROM, stored_dividends

logger = logging.getLogger(__name__)


def _naive_days(dates: Any) -> pd.DatetimeIndex:
    """``dates`` as a normalised, tz-naive ``DatetimeIndex``.

    A tz-aware date keeps its wall-clock day (``tz_localize(None)``), so closes
    and dividends compare on the same calendar days whichever side carries a
    timezone. Mixing the two would otherwise misalign them and silently leave
    the reinvestment factor at 1.0 while still reporting basis ``"total"``.
    """
    index = pd.DatetimeIndex(pd.to_datetime(dates))
    if index.tz is not None:
        index = index.tz_localize(None)
    return index.normalize()


def _clean_closes(closes: pd.Series) -> pd.Series:
    values = pd.to_numeric(closes, errors="coerce")
    values.index = _naive_days(values.index)
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
    divs.index = _naive_days(divs.index)
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


# ───────────────────────── per-ticker total return (#9370) ─────────────────────────
#
# The one path consumers use to put a ticker's stored closes on a total-return
# basis. ``return_basis`` says which basis the caller actually got:
#
# * ``"total"``: an actions file is stored for the ticker. A file with no
#   dividends is a genuine total return that happens to equal price return,
#   provided it is confirmed from the first close on (#9567, see below).
# * ``"price"``: no actions file (or no native ``Close`` to scale), so the
#   dividend history is unknown. The closes come back unchanged rather than
#   being treated as "no dividends paid".
#
# A file with no dividends whose ``confirmed_from`` is later than the first
# close (a rolling fetch that only checked the last few days) is "unknown"
# for the closes before it, so it is price basis too. A file without
# ``confirmed_from`` (written before #9567) keeps reading as total.

TOTAL_RETURN_BASIS = "total"
PRICE_RETURN_BASIS = "price"

DividendLoader = Callable[[str, str], "pd.Series | None"]

# A no-dividend file confirmed from up to this long after the first close still
# covers it: a fetch window starting on a weekend or holiday is no gap.
CONFIRMED_GRACE = pd.Timedelta(days=7)

# ``close`` plus the ``close_<ccy>`` columns ``load_meta_timeseries_range`` adds.
_NATIVE_CLOSE = "close"
_CONVERTED_CLOSE_PREFIX = "close_"


def reinvestment_factor(closes: pd.Series, dividends: pd.Series | None) -> pd.Series:
    """Cumulative growth from reinvested dividends on each close: ``total_return_index / close``.

    1.0 until the first dividend in the window. Being a ratio, it applies to the
    same closes in any currency or scale (``Close_gbp``, pence vs pounds).
    """
    clean = _clean_closes(closes)
    if clean.empty:
        return clean
    return total_return_index(clean, dividends) / clean


def _factor_on(dates: Any, closes: pd.Series, dividends: pd.Series) -> np.ndarray:
    """The reinvestment factor of ``closes`` aligned to ``dates`` (1.0 before the first close)."""
    factor = reinvestment_factor(closes, dividends)
    keys = _naive_days(dates)
    if factor.empty:
        return np.ones(len(keys))
    return factor.reindex(keys, method="ffill").fillna(1.0).to_numpy()


@lru_cache(maxsize=1024)
def _report_price_fallback(ticker: str, exchange: str, reason: str) -> None:
    """Log, once per ticker and reason, that a consumer fell back to price return."""
    logger.info(
        "Price return used for %s.%s: %s",
        sanitise_log_value(ticker),
        sanitise_log_value(exchange),
        sanitise_log_value(reason),
    )


def _dividends_for(
    ticker: str, exchange: str, load_dividends: DividendLoader | None, first_close: pd.Timestamp | None = None
) -> pd.Series | None:
    """Stored dividends, or ``None`` (reported) when the dividend history before ``first_close`` is unknown.

    That is when the ticker has no actions file, or its file has no dividends
    but is only confirmed from after ``first_close`` (``attrs[CONFIRMED_FROM]``).
    ``load_dividends`` defaults to :func:`stored_dividends`, looked up at call time.
    """
    loader = load_dividends or stored_dividends
    try:
        dividends = loader(ticker, exchange)
    except ValueError as exc:  # identifier the store refuses as a file name
        _report_price_fallback(ticker, exchange, f"no corporate actions store entry ({exc})")
        return None
    if dividends is None:
        _report_price_fallback(ticker, exchange, "no stored corporate actions")
        return None
    confirmed = dividends.attrs.get(CONFIRMED_FROM)
    if dividends.empty and confirmed is not None and first_close is not None:
        if pd.Timestamp(confirmed) > pd.Timestamp(first_close) + CONFIRMED_GRACE:
            day = pd.Timestamp(confirmed).date().isoformat()
            _report_price_fallback(ticker, exchange, f"no dividends stored, but only confirmed from {day}")
            return None
    return dividends


def _first_close(closes: pd.Series) -> pd.Timestamp | None:
    clean = _clean_closes(closes)
    return None if clean.empty else clean.index[0]


def total_return_closes(
    closes: pd.Series,
    ticker: str,
    exchange: str,
    *,
    load_dividends: DividendLoader | None = None,
) -> tuple[pd.Series, str]:
    """``closes`` (indexed by date) with dividends reinvested, and the ``return_basis`` used.

    The result keeps the index, units and missing values of ``closes``; only
    the level changes after each ex-date. Without an actions file the closes
    come back unchanged with basis ``"price"``, as they do when the file has no
    dividends but is only confirmed from after the first close.
    """
    values = pd.to_numeric(closes, errors="coerce")
    dividends = _dividends_for(ticker, exchange, load_dividends, _first_close(values))
    if dividends is None:
        return closes, PRICE_RETURN_BASIS
    factor = pd.Series(_factor_on(values.index, values, dividends), index=values.index)
    return values * factor, TOTAL_RETURN_BASIS


def total_return_closes_for(
    closes: pd.Series,
    full_ticker: str,
    *,
    load_dividends: DividendLoader | None = None,
) -> tuple[pd.Series, str]:
    """:func:`total_return_closes` for a ``SYMBOL.EXCHANGE`` ticker; price basis without an exchange."""
    symbol, exchange = split_ticker(full_ticker)
    if not symbol or not exchange:
        _report_price_fallback(symbol or str(full_ticker), exchange or "", "ticker has no exchange")
        return closes, PRICE_RETURN_BASIS
    return total_return_closes(closes, symbol, exchange, load_dividends=load_dividends)


def _frame_dates(df: pd.DataFrame, columns: dict[str, Any]) -> Any:
    """The dates of ``df``'s rows: its ``Date`` column, else a non-numeric index, else ``None``.

    A numeric index (e.g. the ``RangeIndex`` of a cache frame that lost its
    ``Date`` column) would parse as 1970 epoch offsets, never matching a
    dividend, so it is refused rather than read as dates.
    """
    if "date" in columns:
        return df[columns["date"]]
    if pd.api.types.is_numeric_dtype(df.index):
        return None
    return df.index


def total_return_frame(
    df: pd.DataFrame,
    ticker: str,
    exchange: str,
    *,
    load_dividends: DividendLoader | None = None,
) -> tuple[pd.DataFrame, str]:
    """A copy of a timeseries frame with every close column on a total-return basis.

    The factor comes from the native ``Close`` (the units dividends are stored
    in) and scales ``Close`` and each converted ``Close_<ccy>`` column; open,
    high, low and volume are untouched. Dates come from a ``Date`` column, or
    the index when there is none. Returns ``(df, "price")`` unchanged when the
    frame is empty, has no native ``Close``, has no dates (no ``Date`` column
    and a numeric index such as a ``RangeIndex``) or the ticker has no actions
    file.
    """
    if df is None or df.empty:
        return df, PRICE_RETURN_BASIS
    columns = {str(col).lower(): col for col in df.columns}
    native = columns.get(_NATIVE_CLOSE)
    if native is None:
        _report_price_fallback(ticker, exchange, "no native Close column to scale")
        return df, PRICE_RETURN_BASIS
    dates = _frame_dates(df, columns)
    if dates is None:
        _report_price_fallback(ticker, exchange, "no Date column or date index to align dividends to")
        return df, PRICE_RETURN_BASIS
    closes = pd.Series(pd.to_numeric(df[native], errors="coerce").to_numpy(), index=_naive_days(dates))
    dividends = _dividends_for(ticker, exchange, load_dividends, _first_close(closes))
    if dividends is None:
        return df, PRICE_RETURN_BASIS
    # Each row's factor comes from that row's date and native close; keyed by the
    # frame's own index so every close column is scaled row-for-row by label.
    factor = pd.Series(_factor_on(closes.index, closes, dividends), index=df.index)
    out = df.copy()
    for lower, col in columns.items():
        if lower == _NATIVE_CLOSE or lower.startswith(_CONVERTED_CLOSE_PREFIX):
            out[col] = pd.to_numeric(out[col], errors="coerce") * factor
    return out, TOTAL_RETURN_BASIS
