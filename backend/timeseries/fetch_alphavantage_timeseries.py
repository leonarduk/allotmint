import logging
import re
from datetime import date, timedelta

import pandas as pd
import requests

from backend import config_module
from backend.common.url_validator import validate_external_url
from backend.logging_setup import sanitise_log_value
from backend.timeseries.ticker_validator import is_valid_ticker, record_skipped_ticker
from backend.utils.timeseries_helpers import STANDARD_COLUMNS, round_price_columns

cfg = getattr(config_module, "settings", config_module.config)
config = cfg

# Setup logger
logger = logging.getLogger(__name__)

BASE_URL = "https://www.alphavantage.co/query"

# Price basis (#9340): stored closes are the traded price, split-adjusted but not
# dividend-adjusted, matching Yahoo with ``auto_adjust=False``. In
# TIME_SERIES_DAILY_ADJUSTED, ``4. close`` is the raw as-traded close (adjusted
# for neither splits nor dividends) and ``5. adjusted close`` is adjusted for
# both, so neither is that basis on its own. ``4. close`` is used and divided by
# the product of every later ``8. split coefficient`` (1.0 on non-split days) so
# rows before a split line up with Yahoo's; volume is multiplied by the same
# factor. ``5. adjusted close`` is never stored.
PRICE_FIELDS = {"1. open": "Open", "2. high": "High", "3. low": "Low", "4. close": "Close"}
VOLUME_FIELD = "6. volume"
SPLIT_COEFFICIENT_FIELD = "8. split coefficient"


class AlphaVantageRateLimitError(RuntimeError):
    """Raised when the Alpha Vantage rate limit has been exceeded."""

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def _build_symbol(ticker: str, exchange: str) -> str:
    exchange_map = {
        "L": ".LON",
        "LSE": ".LON",
        "UK": ".LON",
        "NASDAQ": "",
        "NYSE": "",
        "US": "",
        "N": "",
        "XETRA": ".DE",
        "DE": ".DE",
        "TSX": ".TOR",
        "ASX": ".AX",
        "F": ".FRA",
    }
    suffix = exchange_map.get(exchange.upper(), "")
    ticker = ticker.upper()
    if ticker.endswith(suffix):
        return ticker
    return ticker + suffix


def split_adjust(df: pd.DataFrame) -> pd.DataFrame:
    """Split-adjust a date-ascending Alpha Vantage frame in place; return it.

    Each row's OHLC is divided, and its volume multiplied, by the product of the
    split coefficients on all *later* rows. A missing, non-numeric or
    non-positive coefficient counts as 1.0 (no split). Without a
    ``8. split coefficient`` column the frame is returned unchanged. Must run on
    the full history before it is cut to the requested range: a split after the
    range's end still rescales the rows inside it.
    """
    if SPLIT_COEFFICIENT_FIELD not in df.columns:
        return df
    coef = pd.to_numeric(df[SPLIT_COEFFICIENT_FIELD], errors="coerce")
    coef = coef.where(coef > 0, 1.0).fillna(1.0)
    later = coef[::-1].cumprod()[::-1].shift(-1, fill_value=1.0)
    if (later == 1.0).all():
        return df
    for col in PRICE_FIELDS.values():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce") / later
    if "Volume" in df.columns:
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce") * later
    return df


def _parse_retry_after(response: requests.Response, message: str) -> int | None:
    """Extract retry delay from headers or message if available."""
    ra = response.headers.get("Retry-After")
    if ra:
        try:
            return int(ra)
        except ValueError:
            pass
    match = re.search(r"(\d+)\s*(seconds?|minutes?)", message, re.IGNORECASE)
    if match:
        delay = int(match.group(1))
        unit = match.group(2).lower()
        if unit.startswith("min"):
            delay *= 60
        return delay
    return None


def fetch_alphavantage_timeseries_range(
    ticker: str,
    exchange: str,
    start_date: date,
    end_date: date,
    api_key: str | None = None,
) -> pd.DataFrame:
    """Fetch historical Alpha Vantage data using a date range."""
    if api_key is None and not cfg.alpha_vantage_enabled:
        logger.info("Alpha Vantage fetching disabled via config")
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    if not is_valid_ticker(ticker, exchange):
        logger.info(
            "Skipping Alpha Vantage fetch for unrecognized ticker %s.%s",
            sanitise_log_value(ticker),
            sanitise_log_value(exchange),
        )
        record_skipped_ticker(ticker, exchange, reason="unknown")
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    symbol = _build_symbol(ticker, exchange)
    key = api_key or cfg.alpha_vantage_key or "demo"

    params = {
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": symbol,
        "outputsize": "full",
        "apikey": key,
    }

    logger.debug("Fetching Alpha Vantage data for %s from %s to %s", sanitise_log_value(symbol), start_date, end_date)
    validate_external_url(BASE_URL)
    try:
        response = requests.get(BASE_URL, params=params, timeout=30, allow_redirects=False)

        if response.status_code == 429:
            retry_after = _parse_retry_after(response, "")
            raise AlphaVantageRateLimitError("Rate limit exceeded", retry_after)

        response.raise_for_status()
        data = response.json()
        if "Time Series (Daily)" not in data:
            message = (
                data.get("Note")
                or data.get("Error Message")
                or data.get("Information")
                or data.get("Message")
                or "Unexpected response"
            )
            logger.debug("Alpha Vantage raw response for %s: %s", sanitise_log_value(symbol), data)
            lower_msg = message.lower()
            if any(k in lower_msg for k in ["frequency", "limit", "try again"]):
                retry_after = _parse_retry_after(response, lower_msg)
                raise AlphaVantageRateLimitError(message, retry_after)
            raise ValueError(message)

        ts = data["Time Series (Daily)"]
        df = pd.DataFrame.from_dict(ts, orient="index").rename(columns={**PRICE_FIELDS, VOLUME_FIELD: "Volume"})

        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)
        split_adjust(df)  # before the range cut: later splits rescale earlier rows
        df = df.loc[str(start_date) : str(end_date)]
        df.reset_index(inplace=True)
        df.rename(columns={"index": "Date"}, inplace=True)
        df["Date"] = pd.to_datetime(df["Date"]).dt.date

        round_price_columns(df)  # significant figures, not 2 dp (#9369)
        if "Volume" in df.columns:
            df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")

        df["Ticker"] = symbol
        df["Source"] = "AlphaVantage"

        return df[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker", "Source"]]
    except Exception as e:
        logger.error("Failed to fetch Alpha Vantage data for %s: %s", sanitise_log_value(symbol), sanitise_log_value(e))
        raise


def fetch_alphavantage_timeseries(
    ticker: str,
    exchange: str,
    days: int = 365,
    api_key: str | None = None,
) -> pd.DataFrame:
    """Backward-compatible interface to fetch trailing days of data."""
    today = date.today()
    start = today - timedelta(days=days)
    return fetch_alphavantage_timeseries_range(ticker, exchange, start, today, api_key)


if __name__ == "__main__":  # pragma: no cover
    df = fetch_alphavantage_timeseries("IBM", "US", days=30)
    print(df.head())
