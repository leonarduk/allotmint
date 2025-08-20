"""Convenience wrappers for fetching timeseries data.

Exposes ``fetch_yahoo_timeseries`` which is patched in tests.
"""

from __future__ import annotations

from .fetch_yahoo_timeseries import fetch_yahoo_timeseries_period


def fetch_yahoo_timeseries(ticker: str, period: str = "1y", interval: str = "1d"):
    """Return a DataFrame of Yahoo price history for ``ticker``.

    ``ticker`` may include an exchange suffix (e.g. ``"ABC.L"``). The
    suffix is split off and passed separately to the underlying helper.
    """
    symbol, exchange = (ticker.split(".", 1) + ["US"])[:2]
    return fetch_yahoo_timeseries_period(symbol, exchange, period=period, interval=interval)


__all__ = ["fetch_yahoo_timeseries"]
