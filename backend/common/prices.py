"""
Price utilities — portfolio-driven (no securities.csv).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Any, Optional, Set, Iterable

import os
import pandas as pd

from backend.common.portfolio_loader import list_portfolios
from backend.common.portfolio_utils import list_all_unique_tickers
from backend.timeseries.fetch_meta_timeseries import run_all_tickers, get_latest_closing_prices, logger, \
    fetch_meta_timeseries

logging.basicConfig(level=logging.DEBUG)


# ──────────────────────────────────────────────────────────────
# securities universe = all tickers we actually hold
# ──────────────────────────────────────────────────────────────
def _build_securities_from_portfolios() -> dict[str, dict]:
    securities: dict[str, dict] = {}
    for p in list_portfolios():
        for acct in p.get("accounts", []):
            for h in acct.get("holdings", []):
                tkr = (h.get("ticker") or "").upper()
                if not tkr:
                    continue
                securities[tkr] = {
                    "ticker": tkr,
                    "name": h.get("name", tkr),
                }
    return securities


_SECURITIES: dict[str, dict] = _build_securities_from_portfolios()


def get_security_meta(ticker: str) -> Optional[dict]:
    return _SECURITIES.get(ticker.upper())


# ──────────────────────────────────────────────────────────────
# latest-price cache
# ──────────────────────────────────────────────────────────────
_price_cache: dict[str, float] = {}


def get_price_gbp(ticker: str) -> Optional[float]:
    return _price_cache.get(ticker.upper())


# ──────────────────────────────────────────────────────────────
# refresh logic
# ──────────────────────────────────────────────────────────────
from backend.timeseries.fetch_meta_timeseries import get_latest_closing_prices

def refresh_prices():
    tickers = list_all_unique_tickers()  # Make sure this returns usable tickers like ["VWRL", "PHGP.L", ...]

    logger.info(f"📊 Fetching latest prices for: {tickers}")

    prices = get_latest_closing_prices(tickers)
    logger.debug(f"✅ Prices fetched: {prices}")

    path = "data/prices/latest_prices.json"
    with open(path, "w") as f:
        json.dump(prices, f, indent=2)

    return {"tickers": tickers, "prices": prices}


# ──────────────────────────────────────────────────────────────
# handy helper for ad-hoc analysis
# ──────────────────────────────────────────────────────────────
def load_latest_prices(tickers: list[str] = None) -> dict[str, float]:
    """
    Load latest known close prices using fetch_meta_timeseries.

    Args:
        tickers: Optional list of tickers. If None, nothing will be returned.

    Returns:
        Dictionary of {ticker: latest_close_price}.
    """
    if not tickers:
        return {}

    prices = {}
    for tkr in tickers:
        df = fetch_meta_timeseries(tkr)
        if df is not None and not df.empty:
            last_row = df.iloc[-1]
            prices[tkr] = float(last_row["close"])
    return prices

import json

from datetime import datetime, timedelta
from typing import Iterable
import pandas as pd

def load_prices_for_tickers(tickers: Iterable[str], exchange: str = "L", days: int = 365) -> pd.DataFrame:
    """
    Load historical prices for a list of tickers using the meta fetch system.

    Args:
        tickers: Iterable of ticker symbols (e.g., ["GRG", "VWRL"])
        exchange: Exchange code (default "L")
        days: How many days back to fetch

    Returns:
        A concatenated DataFrame with columns like Date, Close, Ticker, etc.
    """
    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=days)
    frames = []

    for t in tickers:
        try:
            cleaned = t.replace(".L", "")  # compatibility with old logic
            df = fetch_meta_timeseries(cleaned, exchange, start_date, end_date)
            if not df.empty:
                df["Ticker"] = cleaned
                frames.append(df)
        except Exception as e:
            print(f"[WARN] Failed to fetch prices for {t}: {e}")

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
