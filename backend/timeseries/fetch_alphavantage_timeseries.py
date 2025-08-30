import logging
from datetime import date, timedelta

import pandas as pd
import requests

from backend.config import config
from backend.timeseries.ticker_validator import is_valid_ticker, record_skipped_ticker
from backend.utils.timeseries_helpers import STANDARD_COLUMNS

# Setup logger
logger = logging.getLogger("alphavantage_timeseries")

BASE_URL = "https://www.alphavantage.co/query"


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


def fetch_alphavantage_timeseries_range(
    ticker: str,
    exchange: str,
    start_date: date,
    end_date: date,
    api_key: str | None = None,
) -> pd.DataFrame:
    """Fetch historical Alpha Vantage data using a date range."""
    if api_key is None and not config.alpha_vantage_enabled:
        logger.info("Alpha Vantage fetching disabled via config")
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    if not is_valid_ticker(ticker, exchange):
        logger.info("Skipping Alpha Vantage fetch for unrecognized ticker %s.%s", ticker, exchange)
        record_skipped_ticker(ticker, exchange, reason="unknown")
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    symbol = _build_symbol(ticker, exchange)
    key = api_key or config.alpha_vantage_key or "demo"

    params = {
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": symbol,
        "outputsize": "full",
        "apikey": key,
    }

    logger.debug("Fetching Alpha Vantage data for %s from %s to %s", symbol, start_date, end_date)
    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
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
            logger.debug("Alpha Vantage raw response for %s: %s", symbol, data)
            raise ValueError(message)

        ts = data["Time Series (Daily)"]
        df = pd.DataFrame.from_dict(ts, orient="index").rename(
            columns={
                "1. open": "Open",
                "2. high": "High",
                "3. low": "Low",
                "4. close": "Close",
                "6. volume": "Volume",
            }
        )

        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)
        df = df.loc[str(start_date) : str(end_date)]
        df.reset_index(inplace=True)
        df.rename(columns={"index": "Date"}, inplace=True)
        df["Date"] = pd.to_datetime(df["Date"]).dt.date

        for col in ["Open", "High", "Low", "Close"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").round(2)
        if "Volume" in df.columns:
            df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")

        df["Ticker"] = symbol
        df["Source"] = "AlphaVantage"

        return df[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker", "Source"]]
    except Exception as e:
        logger.error("Failed to fetch Alpha Vantage data for %s: %s", symbol, e)
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


if __name__ == "__main__":
    df = fetch_alphavantage_timeseries("IBM", "US", days=30)
    print(df.head())
