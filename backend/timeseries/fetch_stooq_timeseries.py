import logging
from datetime import datetime, date, timedelta
import pandas as pd
import requests
from io import StringIO

# Setup logger
logger = logging.getLogger("stooq_timeseries")
logging.basicConfig(level=logging.DEBUG)

BASE_URL = "https://stooq.com/q/d/l/"


def get_stooq_suffix(exchange: str) -> str:
    exchange_map = {
        "L": ".UK", "LSE": ".UK", "UK": ".UK",
        "NASDAQ": ".US", "NYSE": ".US", "US": ".US", "AMEX": ".US",
        "XETRA": ".DE", "DE": ".DE",
        "F": ".F"

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
    suffix = get_stooq_suffix(exchange)
    full_ticker = ticker + suffix

    logger.debug(f"Preparing request for ticker={ticker}, exchange={exchange}, "
                 f"full_ticker={full_ticker}, start_date={start_date}, end_date={end_date}")

    params = {
        "s": full_ticker,
        "d1": format_date(start_date),
        "d2": format_date(end_date),
        "i": "d",
        "d": "d"
    }

    logger.debug(f"Fetching Stooq data with URL: {BASE_URL} and params: {params}")
    try:
        response = requests.get(BASE_URL, params=params)
        if not response.ok:
            raise Exception(f"HTTP error {response.status_code} for {full_ticker}")

        if "Exceeded the daily hits limit" in response.text:
            logger.warning("Stooq: Exceeded the daily hits limit")

        df = pd.read_csv(StringIO(response.text))
        if df.empty:
            raise RuntimeError("No data returned from Stooq")

        if 'Date' not in df.columns or 'Close' not in df.columns:
            raise ValueError(f"Unexpected format for {full_ticker}: columns = {df.columns.tolist()}")

        df['Date'] = pd.to_datetime(df['Date'])
        df.sort_values('Date', inplace=True)
        df['Volume'] = df.get('Volume', None)
        df['Ticker'] = ticker

        logger.info(f"Fetched {len(df)} rows for {full_ticker}")

        df["Source"] = "Stooq"

        return df[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker", "Source"]]

    except Exception as e:
        logger.error(f"Failed to fetch Stooq data for {full_ticker}: {e}")
        raise


def fetch_stooq_timeseries(ticker: str, exchange: str, days: int = 365) -> pd.DataFrame:
    """
    Backward-compatible interface to fetch trailing days of data.
    """
    today = date.today()
    start = today - timedelta(days=days)
    logger.debug(f"Fetching trailing {days} days of data for {ticker} on {exchange}")
    logger.debug(f"Preparing request for ticker={ticker}, exchange={exchange}, start_date={start}, end_date={today}")
    return fetch_stooq_timeseries_range(ticker, exchange, start, today)


if __name__ == "__main__":
    # Example usage
    df = fetch_stooq_timeseries("GRG", "LSE", days=700)
    print(df.head())
