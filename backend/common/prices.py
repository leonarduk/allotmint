"""
Price utilities — portfolio-driven (no securities.csv).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional, Set, Iterable

import os
import pandas as pd

from backend.timeseries.fetch_timeseries import (
    run_all_tickers,
    get_latest_closing_prices,
)
from backend.common.portfolio_loader import list_portfolios


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
def refresh_prices(env: Optional[str] = None) -> Dict[str, Any]:
    global _price_cache, _SECURITIES

    _SECURITIES = _build_securities_from_portfolios()
    tickers: Set[str] = set(_SECURITIES.keys())

    run_all_tickers(sorted(tickers))
    _price_cache = get_latest_closing_prices()

    return {"refreshed": True, "tickers": sorted(tickers), "count": len(_price_cache)}


# ──────────────────────────────────────────────────────────────
# handy helper for ad-hoc analysis
# ──────────────────────────────────────────────────────────────
def load_prices_for_tickers(tickers: Iterable[str]) -> pd.DataFrame:
    run_all_tickers(list(tickers))
    root = Path(os.getenv("TIMESERIES_DIR",
                          "timeseries/data-sample/universe/timeseries"))
    frames = []
    for t in tickers:
        fp = root / "f{t.upper()}.csv"
        if fp.exists():
            frames.append(pd.read_csv(fp))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
