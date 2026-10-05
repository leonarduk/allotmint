import logging
from collections.abc import Mapping
from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

from backend.logging_setup import sanitise_log_value
from backend.timeseries.corporate_actions import (
    actions_from_history,
    record_corporate_actions,
)
from backend.timeseries.ticker_validator import (
    is_valid_ticker,
    record_skipped_ticker,
)
from backend.utils.timeseries_helpers import STANDARD_COLUMNS

# Setup logger
logger = logging.getLogger("yahoo_timeseries")

# Price basis of every Yahoo history call (#9340). Never rely on yfinance's
# default, which is ``auto_adjust=True``: that returns a dividend-adjusted
# Close re-based as of the moment of the fetch, so each rolling overlap
# re-fetch after an ex-date planted a fake price step in the cache.
#
# With ``auto_adjust=False`` the ``Close`` is the traded price, *still
# split-adjusted* by Yahoo (pre-split history is restated in post-split
# units, which is what holdings' unit counts are in) but not adjusted for
# dividends. Dividends and splits come back as separate columns
# (``actions=True``) and are stored by ``corporate_actions``.
YAHOO_PRICE_BASIS = {"auto_adjust": False}
YAHOO_HISTORY_KWARGS = {**YAHOO_PRICE_BASIS, "actions": True}


def _build_full_ticker(ticker: str, exchange: str) -> str:
    """
    Return a Yahoo-compatible symbol, *without* duplicating the suffix.
    Examples:
        _build_full_ticker("XDEV", "L")   -> "XDEV.L"
        _build_full_ticker("XDEV.L", "L") -> "XDEV.L"
    """
    suffix = get_yahoo_suffix(exchange)
    ticker = ticker.upper()

    if ticker.endswith(suffix):  # already has ".L", ".DE", ...
        return ticker
    return ticker + suffix


def get_yahoo_suffix(exchange: str) -> str:
    exchange_map = {
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
        "FX": "=X",
    }
    suffix = exchange_map.get(exchange.upper())
    if suffix is None:
        raise ValueError(f"Unsupported exchange: '{exchange}'")
    return suffix


def normalize_history(df: pd.DataFrame, ticker: str, source: str) -> pd.DataFrame:
    """Standardize Yahoo history output.

    Parameters
    ----------
    df : pd.DataFrame
        Raw DataFrame returned by ``yfinance.Ticker.history``.
    ticker : str
        Ticker symbol to set in the ``Ticker`` column.
    source : str
        Source name for the ``Source`` column.

    Returns
    -------
    pd.DataFrame
        DataFrame with ``STANDARD_COLUMNS`` and normalized data types.
    """

    # Ensure "Date" is a column rather than the index
    df = df.reset_index()

    # Convert DateTime to date objects
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"]).dt.date

    # Round price columns
    for col in ["Open", "High", "Low", "Close"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    # Attach metadata columns
    df["Ticker"] = ticker
    df["Source"] = source

    return df[STANDARD_COLUMNS]


def _history_currency(stock: yf.Ticker) -> str | None:
    """Price currency Yahoo reported with the last ``history`` call, if any."""
    try:
        metadata = stock.history_metadata
    except Exception as exc:
        logger.debug("No Yahoo history metadata: %s", sanitise_log_value(exc))
        return None
    # yfinance 1.7 returns a ``HistoryMetadata`` Mapping, not a dict.
    if not isinstance(metadata, Mapping):
        return None
    currency = metadata.get("currency")
    return currency if isinstance(currency, str) and currency else None


def fetch_yahoo_history(full_ticker: str, start_date: date, end_date: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily traded prices for ``full_ticker`` plus the dividends/splits in that window.

    Returns ``(prices, actions)``: ``prices`` in ``STANDARD_COLUMNS`` on the
    raw basis (see ``YAHOO_HISTORY_KWARGS``), ``actions`` in
    ``corporate_actions.ACTION_COLUMNS``. Raises ``ValueError`` when Yahoo
    returns no rows.
    """
    stock = yf.Ticker(full_ticker)
    raw = stock.history(
        start=start_date,
        end=end_date + pd.Timedelta(days=1),  # include end_date
        interval="1d",
        **YAHOO_HISTORY_KWARGS,
    )
    if raw.empty:
        raise ValueError(f"No data returned for {full_ticker} between {start_date} and {end_date}")
    actions = actions_from_history(raw, currency=_history_currency(stock), source="Yahoo")
    return normalize_history(raw, full_ticker, "Yahoo"), actions


def _store_actions(ticker: str, exchange: str, actions: pd.DataFrame) -> None:
    """Persist fetched dividends/splits; a failure here must not lose the prices."""
    if actions.empty:
        return
    symbol = ticker.split(".")[0]
    try:
        record_corporate_actions(symbol, exchange, actions)
    except Exception as exc:
        logger.warning(
            "Could not store corporate actions for %s.%s: %s",
            sanitise_log_value(symbol),
            sanitise_log_value(exchange),
            sanitise_log_value(exc),
        )


def fetch_yahoo_timeseries_range(
    ticker: str,
    exchange: str,
    start_date: date,
    end_date: date,
    *,
    store_actions: bool = True,
) -> pd.DataFrame:
    """Traded (``auto_adjust=False``) daily prices for ``ticker`` between the dates.

    Dividends and splits returned by the same call are merged into the
    ``corporate_actions`` store unless ``store_actions`` is ``False``.
    """
    if not is_valid_ticker(ticker, exchange):
        logger.info(
            "Skipping Yahoo fetch for unrecognized ticker %s.%s",
            sanitise_log_value(ticker),
            sanitise_log_value(exchange),
        )
        record_skipped_ticker(ticker, exchange, reason="unknown")
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    full_ticker = _build_full_ticker(ticker, exchange)
    logger.debug("Fetching Yahoo data for %s from %s to %s", sanitise_log_value(full_ticker), start_date, end_date)

    try:
        prices, actions = fetch_yahoo_history(full_ticker, start_date, end_date)
    except Exception as e:
        logger.error("Failed to fetch Yahoo data for %s: %s", sanitise_log_value(full_ticker), sanitise_log_value(e))
        raise

    logger.info("Fetched %s rows for %s", sanitise_log_value(len(prices)), sanitise_log_value(full_ticker))
    if store_actions:
        _store_actions(ticker, exchange, actions)
    return prices


def fetch_yahoo_timeseries_period(
    ticker: str,
    exchange: str = "US",
    period: str = "1y",
    interval: str = "1d",
    normalize: bool = True,
) -> pd.DataFrame:
    """Backwards-compatible one-shot period-based fetch.

    Parameters
    ----------
    ticker, exchange, period, interval
        Passed directly to ``yfinance.Ticker.history``.
    normalize : bool, default True
        When ``True`` (the default) the output is passed through
        :func:`normalize_history` which truncates timestamps to ``date``
        objects and attaches metadata columns. For intraday usage set this to
        ``False`` to keep full ``datetime`` values.
    """
    full_ticker = _build_full_ticker(ticker, exchange)
    safe_period = sanitise_log_value(period)
    safe_interval = sanitise_log_value(interval)
    logger.debug(
        "Fetching Yahoo data for %s with period=%r, interval=%r",
        sanitise_log_value(full_ticker),
        safe_period,
        safe_interval,
    )

    try:
        stock = yf.Ticker(full_ticker)
        df = stock.history(period=period, interval=interval, **YAHOO_PRICE_BASIS)
        if df.empty:
            raise ValueError(f"No data returned for {full_ticker}")

        if normalize:
            return normalize_history(df, full_ticker, "Yahoo")

        # For intraday data we keep the timestamp column as-is
        df = df.reset_index()
        if "Datetime" in df.columns and "Date" not in df.columns:
            df = df.rename(columns={"Datetime": "Date"})
        return df

    except Exception as e:
        logger.error("Failed to fetch Yahoo data for %s: %s", sanitise_log_value(full_ticker), sanitise_log_value(e))
        raise


if __name__ == "__main__":  # pragma: no cover
    # Example usage
    today = datetime.today().date()
    cutoff = today - timedelta(days=700)

    df = fetch_yahoo_timeseries_range("IXF", "F", start_date=cutoff, end_date=today)
    print(df.head())
