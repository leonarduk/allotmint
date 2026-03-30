"""
Price utilities driven entirely by the live portfolio universe
(no securities.csv required).  Persists a JSON snapshot with:

    {
      "TICKER": {
        "last_price":      ...,
        "price_currency":  "GBP" | None,
        "change_7d_pct":   ...,
        "change_30d_pct":  ...,
        "last_price_date": "YYYY-MM-DD",
        "last_price_time": "YYYY-MM-DDTHH:MM:SSZ",
        "is_stale":        true
      },
      ...
    }

Note on price_currency semantics
---------------------------------
* ``load_live_prices`` returns GBP-normalised prices, so live snapshots emit
  ``price_currency = "GBP"``.
* ``_load_latest_prices`` also returns GBP-normalised prices, so fallback
  snapshots emit ``price_currency = "GBP"``.
* When no price is available, ``price_currency`` is ``None``.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Dict, List, Optional

import pandas as pd

from backend.common import instrument_api
from backend.common.holding_utils import (
    _is_pence_currency,
    load_latest_prices as _load_latest_prices,
    load_live_prices,
)
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
from backend.utils.pricing_dates import PricingDateCalculator
from backend.utils.timeseries_helpers import _nearest_weekday

logger = logging.getLogger("prices")


def _close_on(sym: str, exch: str, d: date) -> Optional[float]:
    """Fetch the close price in GBP for ``sym.exch`` on or nearest before ``d``.

    Pence-denominated instruments (GBX / GBXP / GBp) are divided by 100.
    All other non-GBP currencies are converted via ``_fx_to_base``.
    Note: ``_close_on`` does not call ``apply_scaling``, so the /100 conversion
    is always applied unconditionally for pence instruments (no scale guard needed).
    """

    snap = _nearest_weekday(d, forward=False)
    df = load_meta_timeseries_range(sym, exch, start_date=snap, end_date=snap)
    if df is None or df.empty:
        return None

    name_map = {c.lower(): c for c in df.columns}
    close_col = (
        name_map.get("close_gbp")
        or name_map.get("close")
        or name_map.get("adj close")
        or name_map.get("adj_close")
    )
    if not close_col:
        return None

    try:
        value = float(df[close_col].iloc[0])
    except Exception:
        return None

    if close_col.lower() != "close_gbp":
        from backend.common.instruments import get_instrument_meta
        from backend.common.portfolio_utils import _fx_to_base

        meta = get_instrument_meta(f"{sym}.{exch}") or get_instrument_meta(sym) or {}
        raw_currency = str(meta.get("currency") or "GBP").strip()
        currency = raw_currency.upper()

        if _is_pence_currency(raw_currency):
            # _close_on does not apply scaling, so always divide by 100.
            value /= 100.0
        elif currency != "GBP":
            value *= _fx_to_base(currency, "GBP", {})

    return value


def get_price_snapshot(tickers: List[str]) -> Dict[str, Dict]:
    """Return last price and 7/30 day % changes for each ticker.

    Uses cached meta timeseries data; callers are responsible for priming the
    cache via ``fetch_meta_timeseries`` beforehand. Missing data results in
    ``None`` values so downstream consumers can skip incomplete entries.

    ``price_currency`` reflects the *actual* currency of ``last_price``:
    - Live-price path: ``load_live_prices`` already converts to GBP → "GBP".
    - Last-close fallback: ``_load_latest_prices`` already converts to GBP
      → "GBP".
    - No-data path: ``None`` (last_price is also None; consumers should skip).
    """

    calc = PricingDateCalculator(today=date.today(), weekday_func=_nearest_weekday)
    last_trading_day = calc.reporting_date
    latest = _load_latest_prices(list(tickers))
    live = load_live_prices(list(tickers))
    now = datetime.now(UTC)

    snapshot: Dict[str, Dict] = {}
    for full in tickers:
        live_info = live.get(full.upper())
        last_close = latest.get(full)
        price = None
        ts: Optional[datetime] = None
        is_stale = True
        # price_currency tracks the currency denomination of `price`.
        # Both live and last-close sources are GBP-normalised at this point.
        # None means no price data was available at all.
        price_currency: Optional[str]

        if live_info:
            price = float(live_info.get("price")) if live_info.get("price") is not None else None
            ts = live_info.get("timestamp")
            if ts:
                is_stale = (now - ts) > timedelta(minutes=15)
            # load_live_prices converts to GBP internally
            price_currency = "GBP"
        elif last_close is not None:
            price = float(last_close)
            # no timestamp -> treat as stale
            # _load_latest_prices already normalises to GBP.
            price_currency = "GBP"
        else:
            # No price data available. Emit None so consumers can distinguish
            # "priced at GBP" from "no data" without guessing.
            price_currency = None

        info = {
            "last_price": price,
            "price_currency": price_currency,
            "change_7d_pct": None,
            "change_30d_pct": None,
            "last_price_date": last_trading_day.isoformat(),
            "last_price_time": ts.isoformat().replace("+00:00", "Z") if ts else None,
            "is_stale": is_stale,
        }

        if price is not None:
            resolved = instrument_api._resolve_full_ticker(full, latest)
            if resolved:
                sym, exch = resolved
            else:
                sym = full.split(".", 1)[0]
                exch = "L"
                logger.debug("Could not resolve exchange for %s; defaulting to L", full)

            px_7_candidate = calc.reporting_date - timedelta(days=7)
            px_30_candidate = calc.reporting_date - timedelta(days=30)

            px_7 = _close_on(sym, exch, px_7_candidate)
            px_30 = _close_on(sym, exch, px_30_candidate)

            if px_7 not in (None, 0):
                info["change_7d_pct"] = (float(price) / px_7 - 1.0) * 100.0
            if px_30 not in (None, 0):
                info["change_30d_pct"] = (float(price) / px_30 - 1.0) * 100.0

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
    if not config.prices_json:
        raise RuntimeError("config.prices_json not configured")
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
    ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
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
    calc = PricingDateCalculator(today=date.today(), weekday_func=_nearest_weekday)
    start_candidate = calc.today - timedelta(days=365)
    end_candidate = calc.today - timedelta(days=1)
    start_date = calc.resolve_weekday(start_candidate, forward=False)
    end_date = calc.resolve_weekday(end_candidate, forward=False)

    prices: Dict[str, float] = {}
    for full in tickers:
        resolved = instrument_api._resolve_full_ticker(full, prices)
        if resolved:
            ticker_only, exchange = resolved
        else:
            ticker_only = full.split(".", 1)[0]
            exchange = "L"
            logger.debug("Could not resolve exchange for %s; defaulting to L", full)
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
    calc = PricingDateCalculator(today=date.today(), weekday_func=_nearest_weekday)
    start_date, end_date = calc.lookback_range(days, end=calc.today, forward_end=True)

    frames: List[pd.DataFrame] = []

    for full in tickers:
        try:
            resolved = instrument_api._resolve_full_ticker(full, {})
            if resolved:
                ticker_only, exchange = resolved
            else:
                ticker_only = full.split(".", 1)[0]
                exchange = "L"
                logger.debug("Could not resolve exchange for %s; defaulting to L", full)
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
if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(refresh_prices(), indent=2))
