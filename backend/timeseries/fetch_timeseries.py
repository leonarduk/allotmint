import os
from typing import List, Dict

import pandas as pd
import yfinance as yf

DATA_DIR = "backend/timeseries/data-sample/universe/timeseries"


def fetch_yahoo_timeseries(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    print(f"Fetching data for {ticker} from Yahoo Finance...")
    stock = yf.Ticker(ticker)
    df = stock.history(period=period, interval=interval)
    df.reset_index(inplace=True)
    df["Ticker"] = ticker
    df["Date"] = pd.to_datetime(df["Date"]).dt.date  # clean date format

    # Round price columns to 2 decimal places
    for col in ["Open", "High", "Low", "Close"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    df = df[["Date", "Open", "High", "Low", "Close", "Volume", "Ticker"]]
    return df


def save_to_csv(df: pd.DataFrame, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved CSV to {output_path}")
    return output_path


def run_all_tickers(tickers: List[str], output_dir: str = DATA_DIR) -> List[str]:
    output_files = []
    for ticker in tickers:
        output_files.append(save_ticker_series_to_file(output_dir, ticker))

    return output_files


def save_ticker_series_to_file(output_dir, ticker):
    try:
        df = fetch_yahoo_timeseries(ticker)
        output_path = os.path.join(output_dir, f"{ticker}_timeseries.csv")
        save_to_csv(df, output_path)
    except Exception as e:
        print(f"Failed to fetch {ticker}: {e}")
    return output_path


def load_timeseries_data(output_dir: str = DATA_DIR) -> Dict[str, pd.DataFrame]:
    data = {}
    for file in os.listdir(output_dir):
        if file.endswith("_timeseries.csv"):
            ticker = file.replace("_timeseries.csv", "")
            df = pd.read_csv(os.path.join(output_dir, file), parse_dates=["Date"])
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
        "BP.L",
        "XDEV.L",
        "IEFV.L",
        "VWRL.L",
        "JEGI.L",
        "SERE.L",
        "0P0001BLQI.L"  # Morningstar tickers often fail on Yahoo
    ]
    run_all_tickers(tickers)
    # Example use in main app
    all_data = load_timeseries_data()
    print(f"Loaded {len(all_data)} time series: {list(all_data.keys())}")

