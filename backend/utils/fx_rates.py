import logging
from datetime import date, timedelta
from functools import lru_cache

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Map of base -> quote -> ticker used by yfinance.  When a pair is missing we
# fall back to the generic "BASEQUOTE=X" symbol which Yahoo Finance supports for
# most combinations.
PAIR_MAP: dict[str, dict[str, str]] = {
    "USD": {"GBP": "USDGBP=X", "EUR": "USDEUR=X"},
    "EUR": {"GBP": "EURGBP=X", "USD": "EURUSD=X"},
    "GBP": {"USD": "GBPUSD=X", "EUR": "GBPEUR=X"},
    "CHF": {"GBP": "CHFGBP=X"},
    "JPY": {"GBP": "JPYGBP=X"},
    "CAD": {"GBP": "CADGBP=X"},
}


# Fallback constants used when remote fetch fails. Values are approximate and
# only intended for tests/offline scenarios.
FALLBACK_RATES: dict[tuple[str, str], float] = {
    ("USD", "GBP"): 0.8,
    ("EUR", "GBP"): 0.9,
    ("GBP", "USD"): 1.25,
    ("EUR", "USD"): 1.1,
}


@lru_cache(maxsize=32)
def fetch_fx_rate_range(base: str, quote: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Return FX rates expressed as ``quote`` per unit of ``base``.

    Falls back to a constant for common pairs if the remote fetch fails.
    """

    base = base.upper()
    quote = quote.upper()

    if base == quote:
        dates = pd.bdate_range(start_date, end_date).date
        return pd.DataFrame({"Date": dates, "Rate": [1.0] * len(dates)})

    pair = PAIR_MAP.get(base, {}).get(quote)
    if pair is None:
        pair = f"{base}{quote}=X"

    try:
        ticker = yf.Ticker(pair)
        df = ticker.history(
            start=start_date, end=end_date + timedelta(days=1), interval="1d"
        )
        if not df.empty:
            df.reset_index(inplace=True)
            df["Date"] = pd.to_datetime(df["Date"]).dt.date
            return df[["Date", "Close"]].rename(columns={"Close": "Rate"}).copy()
    except Exception as exc:
        logger.info("FX fetch failed for %s/%s: %s", base, quote, exc)

    dates = pd.bdate_range(start_date, end_date).date
    const = FALLBACK_RATES.get((base, quote))
    if const is None:
        inv = FALLBACK_RATES.get((quote, base))
        const = 1 / inv if inv else 1.0
    return pd.DataFrame({"Date": dates, "Rate": [const] * len(dates)})
