import logging
from datetime import date, timedelta
from functools import lru_cache

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

PAIR_MAP = {
    "USD": "USDGBP=X",
    "EUR": "EURGBP=X",
}


@lru_cache(maxsize=32)
def fetch_fx_rate_range(base: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Return GBP conversion rates for *base* currency.

    Falls back to a constant if remote fetch fails.
    """
    base = base.upper()
    pair = PAIR_MAP.get(base)
    if pair is None:
        raise ValueError(f"Unsupported currency: {base}")

    try:
        ticker = yf.Ticker(pair)
        df = ticker.history(start=start_date, end=end_date + timedelta(days=1), interval="1d")
        if not df.empty:
            df.reset_index(inplace=True)
            df["Date"] = pd.to_datetime(df["Date"]).dt.date
            return df[["Date", "Close"]].rename(columns={"Close": "Rate"}).copy()
    except Exception as exc:
        logger.info("FX fetch failed for %s: %s", base, exc)

    dates = pd.bdate_range(start_date, end_date).date
    const = 0.8 if base == "USD" else 0.9
    return pd.DataFrame({"Date": dates, "Rate": [const] * len(dates)})
