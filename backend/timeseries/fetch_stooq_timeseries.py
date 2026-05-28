import logging
from datetime import date, timedelta
from io import StringIO

import pandas as pd
import requests

from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.timeseries.ticker_validator import is_valid_ticker, record_skipped_ticker
from backend.utils.timeseries_helpers import STANDARD_COLUMNS

logger = logging.getLogger("stooq_timeseries")

BASE_URL = "https://stooq.com/q/d/l/"


class StooqRateLimitError(RuntimeError):
    """Raised when the Stooq daily hit limit has been exceeded."""


# Stooq requests are disabled until this date if the rate limit is hit
STOOQ_DISABLED_UNTIL: date = date.min


def get_stooq_suffix(exchange: str) -> str:
    exchange_map = {
        "L": ".UK", "LSE": ".UK", "UK": ".UK", "LON": ".UK", "XLON": ".UK",
        "NASDAQ": ".US", "NYSE": ".US", "US": ".US", "AMEX": ".US",
        "XETRA": ".DE", "DE": ".DE",
        "F": ".F",
        "TO" : ".TO", "TSX": ".TO"

    }
    suffix = exchange_map.get(exchange.upper())
    if suffix is None:
        raise ValueError(f"Unknown or unsupported exchange: '{exchange}'")
    return suffix


def format_date(d: date) -> str:
    return d.strftime("%Y%m%d")


def fetch_stooq_timeseries_range(
    ticker: str,
    exchange: str,
    start_date: date,
    end_date: date
) -> pd.DataFrame:
    """
    Fetch historical Stooq data using date range.
    """
    global STOOQ_DISABLED_UNTIL
    if date.today() <= STOOQ_DISABLED_UNTIL:
        raise StooqRateLimitError("Exceeded the daily hits limit")
    if not is_valid_ticker(ticker, exchange):
        logger.info("Skipping Stooq fetch for unrecognized ticker %s.%s", ticker, exchange)
        record_skipped_ticker(ticker, exchange, reason="unknown")
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    suffix = get_stooq_suffix(exchange)
    full_ticker = ticker + suffix

    logger.debug(
        "Preparing request for ticker=%s, exchange=%s, full_ticker=%s, start_date=%s, end_date=%s",
        sanitise_log_value(ticker), sanitise_log_value(exchange),
        sanitise_log_value(full_ticker), start_date, end_date,
    )

    params = {
        "s": full_ticker,
        "d1": format_date(start_date),
        "d2": format_date(end_date),
        "i": "d",
        "d": "d"
    }

    logger.debug("Fetching Stooq data with URL: %s and params: %s", BASE_URL, sanitise_log_value(params))
    try:
        response = requests.get(
            BASE_URL,
            params=params,
            timeout=config.stooq_timeout or 10,
        )
        if not response.ok:
            raise Exception(f"HTTP error {response.status_code} for {full_ticker}")

        if "Exceeded the daily hits limit" in response.text:
            logger.warning("Stooq: Exceeded the daily hits limit")
            STOOQ_DISABLED_UNTIL = date.today() + timedelta(days=1)
            raise StooqRateLimitError("Exceeded the daily hits limit")

        df = pd.read_csv(StringIO(response.text))
        if df.empty:
            raise RuntimeError("No data returned from Stooq")

        if 'Date' not in df.columns or 'Close' not in df.columns:
            raise ValueError(f"Unexpected format for {full_ticker}: columns = {df.columns.tolist()}")

        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        df.sort_values('Date', inplace=True)
        df['Volume'] = df.get('Volume', None)
        df['Ticker'] = ticker

        logger.info("Fetched %d rows for %s", len(df), sanitise_log_value(full_ticker))

        df["Source"] = "Stooq"

        return df[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker", "Source"]]

    except requests.exceptions.Timeout:
        logger.warning("Stooq request timed out for %s", full_ticker)
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    except Exception as e:
        logger.error("Failed to fetch Stooq data for %s: %s", sanitise_log_value(full_ticker), sanitise_log_value(e))
        raise


def fetch_stooq_timeseries(ticker: str, exchange: str, days: int = 365) -> pd.DataFrame:
    """
    Backward-compatible interface to fetch trailing days of data.
    """
    today = date.today()
    start = today - timedelta(days=days)
    logger.debug(
        "Fetching trailing %d days of data for %s on %s",
        days, sanitise_log_value(ticker), sanitise_log_value(exchange),
    )
    logger.debug(
        "Preparing request for ticker=%s, exchange=%s, start_date=%s, end_date=%s",
        sanitise_log_value(ticker), sanitise_log_value(exchange), start, today,
    )
    return fetch_stooq_timeseries_range(ticker, exchange, start, today)


if __name__ == "__main__":  # pragma: no cover
    # Example usage
    df = fetch_stooq_timeseries("GRG", "LSE", days=700)
    print(df.head())
