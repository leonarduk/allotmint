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
from backend.timeseries.fetch_meta_timeseries import run_all_tickers, get_latest_closing_prices, logger

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
def load_prices_for_tickers(tickers: Iterable[str]) -> pd.DataFrame:
    run_all_tickers(list(tickers))
    root = Path(os.getenv("TIMESERIES_DIR",
                          "data/universe/timeseries"))
    frames = []
    for t in tickers:
        fp = root / "f{t.upper()}.csv"
        if fp.exists():
            frames.append(pd.read_csv(fp))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

import json

def save_latest_prices_to_file(prices: Dict[str, float], path: str = "data/prices/latest_prices.json"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(prices, f, indent=2)
