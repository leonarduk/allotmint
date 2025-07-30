import os
import logging
from typing import List, Dict

import pandas as pd
import yfinance as yf

# Setup logger
logger = logging.getLogger("yahoo_timeseries")
logging.basicConfig(level=logging.DEBUG)

DATA_DIR = "backend/timeseries/data-sample/universe/timeseries"

def get_yahoo_suffix(exchange: str) -> str:
    """
    Maps exchange name to Yahoo Finance suffix.
    """
    exchange_map = {
        "LSE": ".L",
        "L": ".L",
        "UK": ".L",
        "NASDAQ": "",
        "NYSE": "",
        "US": "",
        "PARIS": ".PA",
        "XETRA": ".DE",
        "DE": ".DE",
        "TSX": ".TO",
        "ASX": ".AX"
    }
    suffix = exchange_map.get(exchange.upper())
    if suffix is None:
        raise ValueError(f"Unsupported exchange: '{exchange}'")
    return suffix

def fetch_yahoo_timeseries(
    ticker: str,
    exchange: str = "US",
    period: str = "1y",
    interval: str = "1d"
) -> pd.DataFrame:
    """
    Fetch historical price data from Yahoo Finance.
    """
    full_ticker = ticker + get_yahoo_suffix(exchange)
    logger.debug(f"Fetching data for {full_ticker} from Yahoo Finance...")

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

        df = df[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker"]]
        logger.info(f"Fetched {len(df)} rows for {full_ticker}")
        return df

    except Exception as e:
        logger.error(f"Failed to fetch Yahoo data for {full_ticker}: {e}")
        raise

def save_to_csv(df: pd.DataFrame, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.debug(f"Saved CSV to {output_path}")
    return output_path

def save_ticker_series_to_file(output_dir: str, ticker: str, exchange: str = "US") -> str:
    try:
        df = fetch_yahoo_timeseries(ticker, exchange=exchange)
        full_ticker = ticker + get_yahoo_suffix(exchange)
        output_path = os.path.join(output_dir, f"{full_ticker}_timeseries.csv")
        return save_to_csv(df, output_path)
    except Exception as e:
        logger.warning(f"Failed to fetch {ticker}: {e}")
        return ""

def run_all_tickers(tickers: List[str], exchange: str = "US", output_dir: str = DATA_DIR) -> List[str]:
    output_files = []
    for ticker in tickers:
        path = save_ticker_series_to_file(output_dir, ticker, exchange=exchange)
        if path:
            output_files.append(path)
    return output_files

def load_timeseries_data(output_dir: str = DATA_DIR) -> Dict[str, pd.DataFrame]:
    data = {}
    for file in os.listdir(output_dir):
        if file.endswith("_timeseries.csv"):
            ticker = file.replace("_timeseries.csv", "")
            path = os.path.join(output_dir, file)
            df = pd.read_csv(path, parse_dates=["Date"])
            data[ticker] = df
    return data

def get_latest_closing_prices() -> Dict[str, float]:
    """
    Return latest available closing price for each ticker from CSV timeseries.
    """
    all_data = load_timeseries_data()
    latest_prices = {}
    for ticker, df in all_data.items():
        if not df.empty:
            df_sorted = df.sort_values("Date")
            latest_row = df_sorted.iloc[-1]
            latest_prices[ticker] = float(latest_row["Close"])
    return latest_prices

if __name__ == "__main__":
    tickers = [
        "AAPL",
        "MSFT",
        "BP",
        "XDEV",
        "IEFV",
        "VWRL",
        "JEGI",
        "SERE",
        "0P0001BLQI"  # Morningstar ticker
    ]
    run_all_tickers(tickers, exchange="LSE")  # Change to "US" for US stocks

    all_data = load_timeseries_data()
    logger.info(f"Loaded {len(all_data)} time series: {list(all_data.keys())}")
