"""
Price utilities driven entirely by the live portfolio universe
(no securities.csv required).  Persists a JSON snapshot with:

    {
      "TICKER": {
        "last_price":      …,
        "change_7d_pct":   …,
        "change_30d_pct":  …,
        "last_price_date": "YYYY-MM-DD"
      },
      …
    }
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional, Iterable, Dict, List

import pandas as pd

# ──────────────────────────────────────────────────────────────
# Local imports
# ──────────────────────────────────────────────────────────────
from backend.common.portfolio_loader import list_portfolios
from backend.common.portfolio_utils import list_all_unique_tickers
from backend.timeseries.cache import load_meta_timeseries_range
from backend.timeseries.fetch_meta_timeseries import (
    logger,
    get_price_snapshot,
)
from backend.utils.timeseries_helpers import _nearest_weekday

logging.basicConfig(level=logging.DEBUG)

# ──────────────────────────────────────────────────────────────
# Securities universe : derived from portfolios
# ──────────────────────────────────────────────────────────────
def _build_securities_from_portfolios() -> Dict[str, Dict]:
    securities: Dict[str, Dict] = {}
    portfolios = list_portfolios()
    logger.debug("Loaded %d portfolios", len(portfolios))
    for pf in portfolios:
        for acct in pf.get("accounts", []):
            for h in acct.get("holdings", []):
                tkr = (h.get("ticker") or "").upper()
                if not tkr:
                    continue
                securities[tkr] = {
                    "ticker": tkr,
                    "name": h.get("name", tkr),
                }
    return securities

def get_security_meta(ticker: str) -> Optional[Dict]:
    """Always fetch fresh metadata derived from latest portfolios."""
    return _build_securities_from_portfolios().get(ticker.upper())


# ──────────────────────────────────────────────────────────────
# In-memory latest-price cache (GBP closes only)
# ──────────────────────────────────────────────────────────────
_price_cache: Dict[str, float] = {}

def get_price_gbp(ticker: str) -> Optional[float]:
    """Return the cached last close in GBP, or None if unseen."""
    return _price_cache.get(ticker.upper())

# ──────────────────────────────────────────────────────────────
# Refresh logic
# ──────────────────────────────────────────────────────────────
def refresh_prices() -> Dict:
    """
    Pulls latest close, 7- and 30-day % moves for every ticker in
    the current portfolios.  Writes to JSON and updates the cache.
    """
    tickers: List[str] = list_all_unique_tickers()
    logger.info(f"📊 Updating price snapshot for: {tickers}")

    snapshot = get_price_snapshot(tickers)

    # ---- persist to disk --------------------------------------------------
    path = "data/prices/latest_prices.json"
    path = Path(path)  # create parent dirs if missing
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2))

    # ---- refresh in-memory cache -----------------------------------------
    _price_cache.clear()
    for tkr, info in snapshot.items():
        _price_cache[tkr.upper()] = info["last_price"]

    logger.debug(f"✅ Snapshot written to {path}")
    return {"tickers": tickers, "snapshot": snapshot}

# ──────────────────────────────────────────────────────────────
# Ad-hoc helpers
# ──────────────────────────────────────────────────────────────
def load_latest_prices(tickers: List[str]) -> Dict[str, float]:
    """
    Convenience helper for notebooks / quick scripts:
    returns {'TICKER': last_close_gbp, …}
    """
    if not tickers:
        return {}
    start_date = date.today() - timedelta(days=365)
    end_date = date.today() - timedelta(days=1)

    prices: Dict[str, float] = {}
    for full in tickers:
        ticker_only, exchange = (full.split(".", 1) + ["L"])[:2]
        df = load_meta_timeseries_range(ticker_only, exchange, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            prices[full] = float(df.iloc[-1]["close"])
    return prices

def load_prices_for_tickers(
    tickers: Iterable[str],
    days: int = 365,
) -> pd.DataFrame:
    """
    Fetch historical daily closes for a list of tickers and return a
    concatenated dataframe; keeps each original suffix (e.g. '.L').
    """
    end_date   = _nearest_weekday(datetime.today().date(), forward=True)
    start_date = _nearest_weekday(end_date - timedelta(days=days), forward=False)

    frames: List[pd.DataFrame] = []

    for full in tickers:
        try:
            ticker_only, exchange = (full.split(".", 1) + ["L"])[:2]
            df = load_meta_timeseries_range(ticker_only, exchange, start_date=start_date, end_date=end_date)
            if not df.empty:
                df["Ticker"] = full  # restore suffix for display
                frames.append(df)
        except Exception as exc:
            logger.warning(f"Failed to fetch prices for {full}: {exc}")

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# ──────────────────────────────────────────────────────────────
# CLI test
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(json.dumps(refresh_prices(), indent=2))
