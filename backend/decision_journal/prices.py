"""GBP return series for the decision journal, on a labelled return basis (#10481, #9370)."""

from __future__ import annotations

from datetime import date
from typing import Callable

import pandas as pd

from backend.common.ticker_utils import split_ticker
from backend.timeseries.cache import load_meta_timeseries_range
from backend.timeseries.total_return import PRICE_RETURN_BASIS, total_return_frame

#: ``(ticker, start, end) -> (closes indexed by date, return_basis)``.
SeriesLoader = Callable[[str, date, date], "tuple[pd.Series, str]"]


def load_return_series(full_ticker: str, start: date, end: date) -> tuple[pd.Series, str]:
    """Daily closes of ``full_ticker`` from ``start`` to ``end``, dividends reinvested where stored.

    Returns the GBP close (``Close_gbp``) when the instrument is converted,
    else the native ``Close``; only ratios of the series are used, so pence vs
    pounds does not matter. The basis is ``"total"`` when a corporate-actions
    file is stored for the ticker, else ``"price"`` (see
    :func:`backend.timeseries.total_return.total_return_frame`).
    """
    symbol, exchange = split_ticker(full_ticker)
    if not exchange:
        return pd.Series(dtype=float), PRICE_RETURN_BASIS
    frame = load_meta_timeseries_range(symbol, exchange, start, end)
    if frame.empty or "Date" not in frame.columns:
        return pd.Series(dtype=float), PRICE_RETURN_BASIS
    frame, basis = total_return_frame(frame, symbol, exchange)
    column = "Close_gbp" if "Close_gbp" in frame.columns else "Close"
    closes = pd.Series(pd.to_numeric(frame[column], errors="coerce").to_numpy(), index=pd.to_datetime(frame["Date"]))
    return closes.dropna(), basis
