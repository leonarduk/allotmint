# backend/common/instrument_api.py
"""
Instrument-level helpers for AllotMint
=====================================

Public API
----------

- timeseries_for_ticker(ticker, days=365)
- positions_for_ticker(group_slug, ticker)
- instrument_summaries_for_group(group_slug)   - used by InstrumentTable
"""

from __future__ import annotations

import datetime as dt
import logging
from functools import lru_cache
from typing import Any, Dict, List, Optional, Mapping, Tuple

import pandas as pd

from backend.common.constants import ACCOUNTS, HOLDINGS, OWNER
from backend.common.group_portfolio import build_group_portfolio
from backend.common.holding_utils import load_latest_prices
from backend.common.instruments import list_group_definitions
from backend.common.portfolio_utils import get_security_meta, list_all_unique_tickers
from backend.config import config
from backend.timeseries.cache import (
    has_cached_meta_timeseries,
    load_meta_timeseries_range,
)
from backend.timeseries.fetch_meta_timeseries import run_all_tickers
from backend.timeseries.fetch_yahoo_timeseries import fetch_yahoo_timeseries_period


logger = logging.getLogger("instrument_api")


# ───────────────────────────────────────────────────────────────
# Local helpers
# ───────────────────────────────────────────────────────────────
def _nearest_weekday(d: dt.date, forward: bool) -> dt.date:
    """Move to the nearest weekday in the chosen direction (no weekends)."""
    while d.weekday() >= 5:
        d += dt.timedelta(days=1 if forward else -1)
    return d


def _build_exchange_map(tickers: List[str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for t in tickers:
        sym, ex = (t.split(".", 1) + [None])[:2]
        if ex:
            mapping[sym.upper()] = ex.upper()
            continue
        meta = get_security_meta(t)
        ex_meta = meta.get("exchange") if meta else None
        if ex_meta:
            mapping[sym.upper()] = ex_meta.upper()
    return mapping


def _resolve_full_ticker(ticker: str, latest: Dict[str, float]) -> Optional[tuple[str, str]]:
    """
    Return `(symbol, exchange)` for *ticker*.
    Prefer exact key in latest prices; otherwise consult cached portfolio metadata.
    """
    t = (ticker or "").upper()
    if not t:
        return None
    if "." in t:
        sym, ex = t.split(".", 1)
        return sym, ex
    base = t.split(".", 1)[0]
    for k in latest.keys():
        sym, ex = (k.split(".", 1) + [None])[:2]
        if sym == base and ex:
            return sym, ex
    ex = _TICKER_EXCHANGE_MAP.get(base)
    if ex:
        return base, ex
    return None


# Fallback helper for group-by metadata
def _coerce_group_value(
    value: Any,
    catalogue: Mapping[str, Mapping[str, Any]],
    *,
    treat_as_id: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    if value is None:
        return None, None

    if isinstance(value, Mapping):
        raw_id = value.get("id") or value.get("grouping_id")
        raw_name = value.get("name")
        ident = str(raw_id).strip() if raw_id is not None else None
        if ident:
            name, slug = _coerce_group_value(ident, catalogue, treat_as_id=True)
            if isinstance(raw_name, str) and raw_name.strip():
                return raw_name.strip(), slug or ident
            return name, slug
        if isinstance(raw_name, str):
            return _coerce_group_value(raw_name, catalogue, treat_as_id=treat_as_id)
        return None, None

    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None, None

        if treat_as_id:
            definition = catalogue.get(trimmed)
            if definition:
                ident = str(definition.get("id") or trimmed)
                name_val = definition.get("name")
                if isinstance(name_val, str) and name_val.strip():
                    return name_val.strip(), ident
                return ident, ident
            return trimmed, trimmed

        definition = catalogue.get(trimmed)
        if definition:
            ident = str(definition.get("id") or trimmed)
            name_val = definition.get("name")
            if isinstance(name_val, str) and name_val.strip():
                return name_val.strip(), ident
            return ident, ident

        for definition in catalogue.values():
            name_val = definition.get("name")
            if isinstance(name_val, str) and name_val.strip().lower() == trimmed.lower():
                ident = str(definition.get("id") or trimmed)
                return name_val.strip(), ident

        return trimmed, None

    return None, None


def _resolve_grouping_details(
    *sources: Optional[Mapping[str, Any]],
    current: Optional[Any] = None,
) -> Tuple[Optional[str], Optional[str]]:
    catalogue = list_group_definitions()

    name, slug = _coerce_group_value(current, catalogue)
    if name:
        return name, slug

    for src in sources:
        if not src:
            continue
        name, slug = _coerce_group_value(src.get("grouping_id"), catalogue, treat_as_id=True)
        if name:
            return name, slug
        name, slug = _coerce_group_value(src.get("grouping"), catalogue)
        if name:
            return name, slug
        name, slug = _coerce_group_value(src.get("sector"), catalogue)
        if name:
            return name, slug
        name, slug = _coerce_group_value(src.get("region"), catalogue)
        if name:
            return name, slug

    return None, None


def _derive_grouping(*sources: Optional[Mapping[str, Any]], current: Optional[Any] = None) -> Optional[str]:
    """Return the first non-empty grouping/sector/region from the provided metadata."""

    name, _ = _resolve_grouping_details(*sources, current=current)
    return name


# Load once; callers can restart process to refresh or we can add a reload later.
_ALL_TICKERS: List[str] = list_all_unique_tickers()
_TICKER_EXCHANGE_MAP: Dict[str, str] = _build_exchange_map(_ALL_TICKERS)

# Global cache for the last known price of each instrument.  This is populated
# on demand to avoid network access during module import.  ``create_app`` primes
# this in a background task unless ``config.skip_snapshot_warm`` is set.
_LATEST_PRICES: Dict[str, float] = {}

MIN_PRICE_THRESHOLD = 1e-2
MAX_CHANGE_PCT = float(getattr(config, "max_change_pct", 500.0))


def prime_latest_prices() -> None:
    """Populate ``_LATEST_PRICES`` from timeseries data.

    This may involve network requests.  Callers should ensure it runs in a
    background task if they don't want to block startup.
    """

    global _LATEST_PRICES
    if config.skip_snapshot_warm:
        _LATEST_PRICES = {}
        return
    _LATEST_PRICES = load_latest_prices(_ALL_TICKERS)


def update_latest_prices_from_snapshot(snapshot: Dict[str, Dict[str, Any]]) -> None:
    """Seed ``_LATEST_PRICES`` using an existing price snapshot.

    This avoids network access and provides reasonable defaults until
    :func:`prime_latest_prices` runs.
    """

    global _LATEST_PRICES
    _LATEST_PRICES = {
        t: float(info.get("last_price"))
        for t, info in snapshot.items()
        if isinstance(info, dict)
        and info.get("last_price") is not None
    }


# ───────────────────────────────────────────────────────────────
# Historical close series (GBP where native is GBP, e.g., LSE)
# ───────────────────────────────────────────────────────────────
def timeseries_for_ticker(ticker: str, days: int = 365) -> Dict[str, Any]:
    """Return recent price history for ``ticker``.

    The payload contains the full series under ``prices`` plus shorter windows
    (7/30/180 days) under ``mini``.  This keeps the original behaviour
    (callers previously only consumed the list) while exposing pre-sliced
    subsets that are convenient for sparkline charts.
    """
    empty_payload: Dict[str, Any] = {
        "prices": [],
        "mini": {"7": [], "30": [], "180": []},
    }

    if not ticker:
        return empty_payload

    resolved = _resolve_full_ticker(ticker, _LATEST_PRICES)
    if not resolved:
        return empty_payload
    sym, ex = resolved

    # Only fetch if not cached
    if not has_cached_meta_timeseries(sym, ex):
        try:
            # Best-effort priming; safe to ignore failures since we fall back anyway.
            run_all_tickers([sym], exchange=ex)
        except Exception:
            pass

    today = dt.date.today()
    end_date = today - dt.timedelta(days=1)
    start_date = end_date - dt.timedelta(days=max(1, days))

    df = load_meta_timeseries_range(sym, ex, start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        return empty_payload

    # Normalize column names
    if "Date" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"Date": "date"})
    if "Close" in df.columns and "close" not in df.columns:
        df = df.rename(columns={"Close": "close"})
    if "Close_gbp" in df.columns and "close_gbp" not in df.columns:
        df = df.rename(columns={"Close_gbp": "close_gbp"})
    if "close" not in df.columns and "close_gbp" in df.columns:
        df["close"] = df["close_gbp"]

    if {"date", "close"} - set(df.columns):
        return empty_payload

    # Keep rows within cutoff and make sure date is ISO string
    cutoff = end_date - dt.timedelta(days=days - 1)
    out: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        rd = r["date"]
        if isinstance(rd, (dt.datetime, dt.date)):
            rd = rd.date().isoformat() if isinstance(rd, dt.datetime) else rd.isoformat()
        if rd >= cutoff.isoformat():
            close_val = float(r["close"])
            close_gbp_val = float(r.get("close_gbp", close_val))
            out.append({"date": rd, "close": close_val, "close_gbp": close_gbp_val})
    mini = {
        "7": out[-7:],
        "30": out[-30:],
        "180": out[-180:],
    }
    return {"prices": out, "mini": mini}


def intraday_timeseries_for_ticker(ticker: str) -> Dict[str, Any]:
    """Return ~48 hours of intraday prices for ``ticker``.

    Falls back to end-of-day prices when the instrument type does not support
    intraday quotes or when intraday fetching fails.
    """

    empty_payload: Dict[str, Any] = {"prices": [], "last_price_time": None}
    if not ticker:
        return empty_payload

    meta = get_security_meta(ticker) or {}
    inst_type = meta.get("instrument_type") or meta.get("instrumentType")
    if inst_type and inst_type.lower() in {"pension"}:
        daily = timeseries_for_ticker(ticker, days=2)["prices"]
        prices = [
            {"timestamp": f"{p['date']}T00:00:00", "price": float(p["close"])}
            for p in daily
        ]
        last_time = prices[-1]["timestamp"] if prices else None
        return {"prices": prices, "last_price_time": last_time}

    resolved = _resolve_full_ticker(ticker, _LATEST_PRICES)
    if not resolved:
        return empty_payload
    sym, ex = resolved

    df = None
    for interval in ("5m", "15m"):
        try:
            df = fetch_yahoo_timeseries_period(
                sym, ex, period="5d", interval=interval, normalize=False
            )
            if not df.empty:
                break
        except Exception:
            df = None
    if df is None or df.empty or "Date" not in df.columns:
        daily = timeseries_for_ticker(ticker, days=2)["prices"]
        prices = [
            {"timestamp": f"{p['date']}T00:00:00", "price": float(p["close"])}
            for p in daily
        ]
        last_time = prices[-1]["timestamp"] if prices else None
        return {"prices": prices, "last_price_time": last_time}

    df = df.copy()
    # Ensure datetime comparison uses a consistent timezone by converting to UTC
    # and dropping tzinfo so we can compare against a naive UTC cutoff.
    df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.tz_localize(None)
    cutoff = dt.datetime.utcnow() - dt.timedelta(hours=48)
    df = df[df["Date"] >= cutoff]
    col = "Close_gbp" if "Close_gbp" in df.columns else "Close"

    prices = [
        {"timestamp": r["Date"].to_pydatetime().isoformat(), "price": float(r[col])}
        for _, r in df.iterrows()
    ]
    last_time = prices[-1]["timestamp"] if prices else None
    return {"prices": prices, "last_price_time": last_time}


# ───────────────────────────────────────────────────────────────
# Last price + %-changes helpers
# ───────────────────────────────────────────────────────────────


def _close_on(sym: str, ex: str, d: dt.date) -> Optional[float]:
    """Return close price for ``sym.ex`` ticker on date ``d`` if available."""
    snap = _nearest_weekday(d, forward=False)
    df = load_meta_timeseries_range(sym, ex, start_date=snap, end_date=snap)
    if df is None or df.empty:
        return None
    col = "close_gbp" if "close_gbp" in df.columns else ("Close_gbp" if "Close_gbp" in df.columns else None)
    if col is None:
        col = "close" if "close" in df.columns else ("Close" if "Close" in df.columns else None)
    return float(df[col].iloc[0]) if col else None


def price_change_pct(ticker: str, days: int) -> Optional[float]:
    """Return % change from ``days`` ago to yesterday's close for ``ticker``."""
    today = dt.date.today()
    yday = today - dt.timedelta(days=1)

    resolved = _resolve_full_ticker(ticker, _LATEST_PRICES)
    if not resolved:
        return None

    sym, ex = resolved
    px_now = _close_on(sym, ex, yday)
    px_then = _close_on(sym, ex, yday - dt.timedelta(days=days))
    if px_now is None or px_then is None or px_then == 0:
        return None
    if px_then < MIN_PRICE_THRESHOLD:
        logger.warning("price_change_pct: px_then %.4f below threshold for %s", px_then, ticker)
        return None
    pct = (px_now / px_then - 1.0) * 100.0
    if abs(pct) > MAX_CHANGE_PCT:
        logger.warning(
            "price_change_pct: change %.2f%% exceeds max %.2f%% for %s",
            pct,
            MAX_CHANGE_PCT,
            ticker,
        )
        return None
    return pct


def top_movers(
    tickers: List[str],
    days: int,
    limit: int = 10,
    *,
    min_weight: float = 0.0,
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Return top gainers and losers for ``tickers`` over ``days``.

    Parameters
    ----------
    min_weight:
        Minimum portfolio weight (in percent) required for a ticker to be
        included.  Set to ``0`` to disable filtering.
    weights:
        Optional mapping of ``ticker -> weight_percent`` used for filtering.
    """

    today = dt.date.today()
    yday = today - dt.timedelta(days=1)
    rows: List[Dict[str, Any]] = []
    anomalies: List[str] = []

    for t in tickers:
        if min_weight and weights and weights.get(t, 0.0) < min_weight:
            continue
        change = price_change_pct(t, days)
        if change is None:
            anomalies.append(t)
            continue
        resolved = _resolve_full_ticker(t, _LATEST_PRICES)
        if not resolved:
            continue
        sym, ex = resolved
        full = f"{sym}.{ex}" if ex else sym
        last_px = _close_on(sym, ex, yday)
        meta = get_security_meta(full) or {}
        rows.append(
            {
                "ticker": full,
                "name": meta.get("name", full),
                "change_pct": change,
                "last_price_gbp": last_px,
                "last_price_date": yday.isoformat(),
            }
        )

    pos = sorted(
        [r for r in rows if r["change_pct"] > 0],
        key=lambda r: r["change_pct"],
        reverse=True,
    )
    neg = sorted(
        [r for r in rows if r["change_pct"] < 0],
        key=lambda r: r["change_pct"],
    )
    return {"gainers": pos[:limit], "losers": neg[:limit], "anomalies": anomalies}


@lru_cache(maxsize=2048)
def _price_and_changes(ticker: str) -> Dict[str, Any]:
    """
    Return last price and common percentage changes for ``ticker``.
    """
    today = dt.date.today()
    yday = today - dt.timedelta(days=1)

    resolved = _resolve_full_ticker(ticker, _LATEST_PRICES)
    if not resolved:
        return {
            "last_price_gbp": None,
            "last_price_date": None,
            "last_price_time": None,
            "is_stale": True,
            "change_7d_pct": None,
            "change_30d_pct": None,
        }
    sym, ex = resolved

    from backend.common import portfolio_utils as pu  # local import

    snap = pu._PRICE_SNAPSHOT.get(ticker.upper()) or pu._PRICE_SNAPSHOT.get(sym)
    if isinstance(snap, dict) and snap.get("last_price") is not None:
        last_px = snap.get("last_price")
        last_time = snap.get("last_price_time")
        is_stale = bool(snap.get("is_stale", False))
    else:
        last_px = _close_on(sym, ex, yday)
        last_time = None
        is_stale = True

    return {
        "last_price_gbp": last_px,
        "last_price_date": yday.isoformat(),
        "last_price_time": last_time,
        "is_stale": is_stale,
        "change_7d_pct": price_change_pct(ticker, 7),
        "change_30d_pct": price_change_pct(ticker, 30),
    }


# ───────────────────────────────────────────────────────────────
# Positions by ticker
# ───────────────────────────────────────────────────────────────
def positions_for_ticker(group_slug: str, ticker: str) -> List[Dict[str, Any]]:
    """
    Return enriched positions for the given ticker across a group.
    Uses the already-enriched holdings from group_portfolio (owner added onto each acct).
    """
    gp = build_group_portfolio(group_slug)
    rows: List[Dict[str, Any]] = []

    def _matches(q: str, held: str) -> bool:
        qU, hU = (q or "").upper(), (held or "").upper()
        return hU == qU or hU.split(".", 1)[0] == qU.split(".", 1)[0]

    for acct in gp.get(ACCOUNTS, []):
        owner = acct.get(OWNER)
        acct_type = acct.get("account_type")
        currency = acct.get("currency")
        for h in acct.get(HOLDINGS, []):
            if _matches(ticker, h.get("ticker")) and (h.get("units") or 0):
                rows.append(
                    {
                        "owner": owner,
                        "account_type": acct_type,
                        "currency": currency,
                        "units": h.get("units", 0.0),
                        "current_price_gbp": h.get("current_price_gbp") or h.get("price"),
                        "market_value_gbp": h.get("market_value_gbp"),
                        "book_cost_basis_gbp": h.get("cost_basis_gbp", 0.0),
                        "effective_cost_basis_gbp": h.get("effective_cost_basis_gbp", 0.0),
                        "gain_gbp": h.get("gain_gbp", 0.0),
                        "gain_pct": h.get("gain_pct"),
                        "days_held": h.get("days_held"),
                        "sell_eligible": h.get("sell_eligible"),
                        "days_until_eligible": h.get("days_until_eligible"),
                        "eligible_on": h.get("eligible_on"),
                        "next_eligible_sell_date": h.get("next_eligible_sell_date"),
                    }
                )
    return rows


# ───────────────────────────────────────────────────────────────
# Instrument table rows
# ───────────────────────────────────────────────────────────────
def instrument_summaries_for_group(group_slug: str) -> List[Dict[str, Any]]:
    """
    Aggregate holdings in *group_slug* into per-ticker summary for InstrumentTable.
    Adds last price + 7d/30d % changes (as-of yesterday) via the same pipeline.
    """
    gp = build_group_portfolio(group_slug)
    by_ticker: Dict[str, Dict[str, Any]] = {}

    for acct in gp.get(ACCOUNTS, []):
        for h in acct.get(HOLDINGS, []):
            tkr = (h.get("ticker") or "").strip()
            name = (h.get("name") or "").strip()
            if not tkr or not name:
                continue

            entry = by_ticker.setdefault(
                tkr,
                {
                    "ticker": tkr,
                    "name": name,
                    "units": 0.0,
                    "market_value_gbp": 0.0,
                    "gain_gbp": 0.0,
                },
            )
            entry["units"] += float(h.get("units") or 0.0)
            entry["market_value_gbp"] += float(h.get("market_value_gbp") or 0.0)
            entry["gain_gbp"] += float(h.get("gain_gbp") or 0.0)

    # Decorate with last price + changes
    for tkr, entry in by_ticker.items():
        if not tkr:
            continue
        meta = get_security_meta(tkr) or {}
        entry.setdefault("asset_class", meta.get("asset_class"))
        entry.setdefault("industry", meta.get("industry") or meta.get("sector"))
        entry.setdefault("region", meta.get("region"))
        entry.setdefault("sector", meta.get("sector"))
        grouping_name, grouping_id = _resolve_grouping_details(meta, entry, current=entry.get("grouping"))
        if grouping_id:
            entry["grouping_id"] = grouping_id
        if grouping_name:
            entry["grouping"] = grouping_name
        entry.update(_price_and_changes(tkr))
        cost = entry["market_value_gbp"] - entry["gain_gbp"]
        entry["gain_pct"] = (entry["gain_gbp"] / cost * 100.0) if cost else None

    return sorted(by_ticker.values(), key=lambda r: r["market_value_gbp"], reverse=True)
