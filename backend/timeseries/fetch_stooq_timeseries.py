import logging
from datetime import datetime, timedelta
import pandas as pd
import requests
from io import StringIO

# Setup logger
logger = logging.getLogger("stooq_timeseries")
logging.basicConfig(level=logging.DEBUG)

BASE_URL = "https://stooq.com/q/d/l/"

def get_stooq_suffix(exchange: str) -> str:
    exchange_map = {
        # UK
        "L": ".UK",
        "LSE": ".UK",
        "UK": ".UK",

        # US
        "NYSE": ".US",
        "NASDAQ": ".US",
        "US": ".US",
        "AMEX": ".US",

        # Germany (example)
        "XETRA": ".DE",
        "DE": ".DE"
    }
    suffix = exchange_map.get(exchange.upper())
    if suffix is None:
        raise ValueError(f"Unknown or unsupported exchange: '{exchange}'")
    return suffix

def format_date(d: datetime) -> str:
    return d.strftime("%Y%m%d")

def fetch_stooq_timeseries(ticker: str, exchange: str, days: int = 365) -> pd.DataFrame:
    """
    Fetch historical price data from Stooq.com for a given ticker and exchange.
    """
    suffix = get_stooq_suffix(exchange)
    full_ticker = ticker + suffix
    end_date = datetime.today()
    start_date = end_date - timedelta(days=days)

    params = {
        "s": full_ticker,
        "d1": format_date(start_date),
        "d2": format_date(end_date),
        "i": "d",
        "d": "d"
    }

    logger.debug(f"Fetching Stooq data for {full_ticker} from {params['d1']} to {params['d2']}")
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
            raise ValueError(f"Unexpected format for {full_ticker}")

        df['Date'] = pd.to_datetime(df['Date'])
        df.sort_values('Date', inplace=True)
        df['Volume'] = df.get('Volume', None)
        df['Ticker'] = ticker

        logger.info(f"Fetched {len(df)} rows for {full_ticker}")
        return df[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker"]]

    except Exception as e:
        logger.error(f"Failed to fetch Stooq data for {full_ticker}: {e}")
        raise

if __name__ == "__main__":
    # Example: Apple (AAPL) on NASDAQ
    # df = fetch_stooq_timeseries("AAPL", "NASDAQ", days=365)
    df = fetch_stooq_timeseries("GRG", "LSE", days=365)
    print(df.head())
