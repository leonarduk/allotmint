"""
Price utilities driven entirely by the live portfolio universe
(no securities.csv required).  Persists a JSON snapshot with:

    {
      "TICKER": {
        "last_price":      ...,
        "change_7d_pct":   ...,
        "change_30d_pct":  ...,
        "last_price_date": "YYYY-MM-DD"
      },
      ...
    }
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional, Iterable, Dict, List

import pandas as pd

from backend.common import instrument_api
from backend.common.holding_utils import load_latest_prices as _load_latest_prices
from backend.common.portfolio_loader import list_portfolios
from backend.common.portfolio_utils import (
    list_all_unique_tickers,
    refresh_snapshot_in_memory,
    check_price_alerts,
)
# ──────────────────────────────────────────────────────────────
# Local imports
# ──────────────────────────────────────────────────────────────
from backend.config import config
from backend.timeseries.cache import load_meta_timeseries_range
from backend.utils.timeseries_helpers import _nearest_weekday

logger = logging.getLogger("prices")


def _close_on(sym: str, exch: str, d: date) -> Optional[float]:
    """Fetch the close price for ``sym.exch`` on or nearest before ``d``."""

    snap = _nearest_weekday(d, forward=False)
    df = load_meta_timeseries_range(sym, exch, start_date=snap, end_date=snap)
    if df is None or df.empty:
        return None

    # try a few common column names, prioritising GBP-converted prices
    for col in ("close_gbp", "Close_gbp", "close", "Close"):
        if col in df.columns:
            try:
                return float(df[col].iloc[0])
            except Exception:
                return None
    return None


def get_price_snapshot(tickers: List[str]) -> Dict[str, Dict]:
    """Return last price and 7/30 day % changes for each ticker.

    Uses cached meta timeseries data; callers are responsible for priming the
    cache via ``fetch_meta_timeseries`` beforehand. Missing data results in
    ``None`` values so downstream consumers can skip incomplete entries.
    """

    yday = date.today() - timedelta(days=1)
    latest = _load_latest_prices(list(tickers))

    snapshot: Dict[str, Dict] = {}
    for full in tickers:
        last = latest.get(full)
        info = {
            "last_price": float(last) if last is not None else None,
            "change_7d_pct": None,
            "change_30d_pct": None,
            "last_price_date": yday.isoformat(),
        }

        if last is not None:
            resolved = instrument_api._resolve_full_ticker(full, latest)
            if resolved:
                sym, exch = resolved
            else:
                sym = full.split(".", 1)[0]
                exch = "L"
                logger.debug(
                    "Could not resolve exchange for %s; defaulting to L", full
                )

            px_7 = _close_on(sym, exch, yday - timedelta(days=7))
            px_30 = _close_on(sym, exch, yday - timedelta(days=30))

            if px_7 not in (None, 0):
                info["change_7d_pct"] = (float(last) / px_7 - 1.0) * 100.0
            if px_30 not in (None, 0):
                info["change_30d_pct"] = (float(last) / px_30 - 1.0) * 100.0

        snapshot[full] = info

    return snapshot

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
    logger.info(f"Updating price snapshot for: {tickers}")

    snapshot = get_price_snapshot(tickers)

    # ---- persist to disk --------------------------------------------------
    path = Path(config.prices_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2))

    # ---- refresh in-memory cache -----------------------------------------
    _price_cache.clear()
    for tkr, info in snapshot.items():
        _price_cache[tkr.upper()] = info["last_price"]

    # keep portfolio_utils in sync and run alert checks
    refresh_snapshot_in_memory(snapshot)
    check_price_alerts()

    logger.debug(f"Snapshot written to {path}")
    ts = datetime.utcnow().isoformat() + "Z"
    return {
        "tickers": tickers,
        "snapshot": snapshot,
        "timestamp": ts,
    }

# ──────────────────────────────────────────────────────────────
# Ad-hoc helpers
# ──────────────────────────────────────────────────────────────
def load_latest_prices(tickers: List[str]) -> Dict[str, float]:
    """
    Convenience helper for notebooks / quick scripts:
    returns {'TICKER': last_close_gbp, ...}
    """
    if not tickers:
        return {}
    start_date = date.today() - timedelta(days=365)
    end_date = date.today() - timedelta(days=1)

    prices: Dict[str, float] = {}
    for full in tickers:
        resolved = instrument_api._resolve_full_ticker(full, prices)
        if resolved:
            ticker_only, exchange = resolved
        else:
            ticker_only = full.split(".", 1)[0]
            exchange = "L"
            logger.debug(
                "Could not resolve exchange for %s; defaulting to L", full
            )
        df = load_meta_timeseries_range(
            ticker_only, exchange, start_date=start_date, end_date=end_date
        )
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
            resolved = instrument_api._resolve_full_ticker(full, {})
            if resolved:
                ticker_only, exchange = resolved
            else:
                ticker_only = full.split(".", 1)[0]
                exchange = "L"
                logger.debug(
                    "Could not resolve exchange for %s; defaulting to L", full
                )
            df = load_meta_timeseries_range(
                ticker_only, exchange, start_date=start_date, end_date=end_date
            )
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
