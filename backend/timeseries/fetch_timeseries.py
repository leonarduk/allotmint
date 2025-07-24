import pandas as pd
import yfinance as yf


def fetch_yahoo_timeseries(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    print(f"Fetching data for {ticker} from Yahoo Finance...")
    stock = yf.Ticker(ticker)
    df = stock.history(period=period, interval=interval)
    df.reset_index(inplace=True)
    df["Ticker"] = ticker
    return df

def save_to_csv(df: pd.DataFrame, output_path: str):
    df.to_csv(output_path, index=False)
    print(f"Saved CSV to {output_path}")

if __name__ == "__main__":
    tickers = ["AAPL", "MSFT", "BP.L"]  # Add more as needed
    for ticker in tickers:
        df = fetch_yahoo_timeseries(ticker)
        save_to_csv(df, f"{ticker}_timeseries.csv")
