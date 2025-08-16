import logging
from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf
from backend.timeseries.ticker_validator import is_valid_ticker, record_skipped_ticker
from backend.utils.timeseries_helpers import STANDARD_COLUMNS

# Setup logger
logger = logging.getLogger("yahoo_timeseries")

def _build_full_ticker(ticker: str, exchange: str) -> str:
    """
    Return a Yahoo-compatible symbol, *without* duplicating the suffix.
    Examples:
        _build_full_ticker("XDEV", "L")   -> "XDEV.L"
        _build_full_ticker("XDEV.L", "L") -> "XDEV.L"
    """
    suffix = get_yahoo_suffix(exchange)
    ticker = ticker.upper()

    if ticker.endswith(suffix):        # already has ".L", ".DE", ...
        return ticker
    return ticker + suffix

def get_yahoo_suffix(exchange: str) -> str:
    exchange_map = {
        "LSE": ".L", "L": ".L", "UK": ".L",
        "NASDAQ": "", "NYSE": "", "N": "", "US": "",
        "PARIS": ".PA", "XETRA": ".DE", "DE": ".DE",
        "TSX": ".TO", "TO": ".TO",
        "ASX": ".AX",
        "F": ".F",
        "FX": "=X"
    }
    suffix = exchange_map.get(exchange.upper())
    if suffix is None:
        raise ValueError(f"Unsupported exchange: '{exchange}'")
    return suffix


def fetch_yahoo_timeseries_range(
    ticker: str,
    exchange: str,
    start_date: date,
    end_date: date
) -> pd.DataFrame:
    if not is_valid_ticker(ticker, exchange):
        logger.info("Skipping Yahoo fetch for unrecognized ticker %s.%s", ticker, exchange)
        record_skipped_ticker(ticker, exchange, reason="unknown")
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    full_ticker = _build_full_ticker(ticker, exchange)
    logger.debug(f"Fetching Yahoo data for {full_ticker} from {start_date} to {end_date}")

    try:
        stock = yf.Ticker(full_ticker)
        df = stock.history(
            start=start_date,
            end=end_date + pd.Timedelta(days=1),  # include end_date
            interval="1d"
        )
        if df.empty:
            raise ValueError(f"No data returned for {full_ticker} between {start_date} and {end_date}")

        df.reset_index(inplace=True)
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        df["Ticker"] = full_ticker

        for col in ["Open", "High", "Low", "Close"]:
            if col in df.columns:
                df[col] = df[col].round(2)

        df["Source"] = "Yahoo"

        return df[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker", "Source"]]

    except Exception as e:
        logger.error(f"Failed to fetch Yahoo data for {full_ticker}: {e}")
        raise


def fetch_yahoo_timeseries_period(
    ticker: str,
    exchange: str = "US",
    period: str = "1y",
    interval: str = "1d"
) -> pd.DataFrame:
    """
    Backwards-compatible one-shot period-based fetch. Does NOT use rolling cache.
    """
    full_ticker = _build_full_ticker(ticker, exchange)
    logger.debug(f"Fetching Yahoo data for {full_ticker} with period='{period}', interval='{interval}'")

    try:
        stock = yf.Ticker(full_ticker)
        df = stock.history(period=period, interval=interval)
        if df.empty:
            raise ValueError(f"No data returned for {full_ticker}")

        df.reset_index(inplace=True)
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        df["Ticker"] = full_ticker

        for col in ["Open", "High", "Low", "Close"]:
            if col in df.columns:
                df[col] = df[col].round(2)

        return df[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker"]]

    except Exception as e:
        logger.error(f"Failed to fetch Yahoo data for {full_ticker}: {e}")
        raise

if __name__ == "__main__":
    # Example usage
    today = datetime.today().date()
    cutoff = today - timedelta(days=700)

    df = fetch_yahoo_timeseries_range("IXF", "F", start_date=cutoff, end_date=today)
    print(df.head())
