import logging
from datetime import date, timedelta, datetime
from typing import List, Dict

import pandas as pd

logger = logging.getLogger("meta_timeseries")


def fetch_meta_timeseries(ticker: str, exchange: str, start_date: date, end_date: date) -> pd.DataFrame:
    from backend.timeseries.fetch_yahoo_timeseries import fetch_yahoo_timeseries_range
    from backend.timeseries.fetch_stooq_timeseries import fetch_stooq_timeseries_range
    from backend.timeseries.fetch_ft_timeseries import fetch_ft_timeseries

    sources = []

    # Yahoo
    try:
        df = fetch_yahoo_timeseries_range(ticker, exchange, start_date, end_date)
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        if not df.empty and df["Date"].min() <= start_date and df["Date"].max() >= end_date:
            logger.debug("Yahoo provided complete data range.")
            return df
        sources.append(("yahoo", df))
    except Exception as e:
        logger.warning(f"Yahoo fetch failed: {e}")

    # Stooq
    try:
        df = fetch_stooq_timeseries_range(ticker, exchange, start_date, end_date)
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        if not df.empty and df["Date"].min() <= start_date and df["Date"].max() >= end_date:
            logger.debug("Stooq provided complete data range.")
            return df
        sources.append(("stooq", df))
    except Exception as e:
        logger.warning(f"Stooq fetch failed: {e}")

    # # FT
    # try:
    #     df = fetch_ft_timeseries(ticker)
    #     df["Date"] = pd.to_datetime(df["Date"]).dt.date
    #     if not df.empty and df["Date"].min() <= start_date and df["Date"].max() >= end_date:
    #         logger.debug("FT provided complete data range.")
    #         return df
    #     sources.append(("ft", df))
    # except Exception as e:
    #     logger.warning(f"FT fetch failed: {e}")

    # fallback merge
    logger.warning("No source provided full coverage; merging partial data")
    combined = pd.concat([df for _, df in sources if not df.empty])
    combined = combined.drop_duplicates(subset="Date").sort_values("Date")
    combined["Ticker"] = ticker
    return combined[combined["Date"] >= start_date]

def run_all_tickers(tickers: List[str], exchange: str = "L", days: int = 365) -> List[str]:
    today = datetime.today().date()
    cutoff = today - timedelta(days=days)

    processed = []
    for ticker in tickers:
        try:
            cleaned = ticker.replace(".L", "")
            df = fetch_meta_timeseries(cleaned, exchange, start_date=cutoff, end_date=today)
            if not df.empty:
                processed.append(cleaned)
        except Exception as e:
            print(f"[WARN] Failed to load {ticker}: {e}")
    return processed

def get_latest_closing_prices(tickers: List[str], exchange: str = "L") -> Dict[str, float]:
    all_data = load_timeseries_data(tickers, exchange)
    latest_prices = {}

    for ticker, df in all_data.items():
        if df.empty:
            logger.warning(f"[{ticker}] DataFrame is empty")
            continue
        df_sorted = df.sort_values("Date")
        latest_row = df_sorted.iloc[-1]
        latest_prices[ticker] = float(latest_row["Close"])
        logger.debug(f"[{ticker}] Latest price = {latest_prices[ticker]} on {latest_row['Date']}")

    return latest_prices

def load_timeseries_data(tickers: List[str], exchange: str = "L", days: int = 365) -> Dict[str, pd.DataFrame]:
    today = datetime.today().date()
    cutoff = today - timedelta(days=days)
    result = {}

    for ticker in tickers:
        try:
            df = fetch_meta_timeseries(ticker, exchange, start_date=cutoff, end_date=today)
            if not df.empty:
                result[ticker] = df
        except Exception as e:
            logger.warning(f"Failed to load timeseries for {ticker}: {e}")
    return result

if __name__ == "__main__":
    # Example usage
    today = datetime.today().date()
    cutoff = today - timedelta(days=700)

    df = fetch_meta_timeseries("GRG", "LSE", start_date=cutoff, end_date=today)
    print(df.head())
