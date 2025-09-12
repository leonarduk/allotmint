# backend/common/holding_utils.py
from __future__ import annotations

import datetime as dt
import logging
from datetime import date, timedelta
from typing import Any, Dict, Optional

import pandas as pd
import requests

from backend.common.approvals import is_approval_valid
from backend.common.constants import (
    ACQUIRED_DATE,
    COST_BASIS_GBP,
    EFFECTIVE_COST_BASIS_GBP,
    TICKER,
    UNITS,
)
from backend.common.instruments import get_instrument_meta
from backend.common.user_config import UserConfig
from backend.config import config
from backend.timeseries.cache import load_meta_timeseries_range
from backend.utils.timeseries_helpers import apply_scaling, get_scaling_override

logger = logging.getLogger(__name__)


# ───────────── helpers ─────────────
def _parse_date(val) -> Optional[dt.date]:
    if val is None:
        return None
    if isinstance(val, dt.date) and not isinstance(val, dt.datetime):
        return val
    if isinstance(val, dt.datetime):
        return val.date()
    try:
        return dt.datetime.fromisoformat(str(val)).date()
    except ValueError:
        return None


def _nearest_weekday(d: dt.date, forward: bool) -> dt.date:
    while d.weekday() >= 5:
        d += dt.timedelta(days=1 if forward else -1)
    return d


def _lower_name_map(df: pd.DataFrame) -> Dict[str, str]:
    return {c.lower(): c for c in df.columns}


def load_latest_prices(full_tickers: list[str]) -> dict[str, float]:
    """
    Returns mapping like {'HFEL.L': 3.21, 'IEFV.L': 5.77}.
    Prices are GBP-converted when that column is available.
    - Uses end_date = yesterday
    - Accepts 'HFEL.L' or 'HFEL' (defaults exchange 'L')
    - Skips empties instead of returning 0.00
    """
    result: dict[str, float] = {}
    if not full_tickers:
        return result

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=365)

    from backend.common import instrument_api

    for full in full_tickers:
        resolved = instrument_api._resolve_full_ticker(full, result)
        if resolved:
            ticker, exchange = resolved
        else:
            ticker = full.split(".", 1)[0]
            exchange = "L"
            logger.debug("Could not resolve exchange for %s; defaulting to L", full)

        try:
            df = load_meta_timeseries_range(
                ticker=ticker,
                exchange=exchange,
                start_date=start_date,
                end_date=end_date,
            )
            if df is None or df.empty:
                # no data -> don't write a zero; just continue
                continue

            # apply instrument-specific scaling (e.g., GBX -> GBP)
            scale = get_scaling_override(ticker, exchange, None)
            df = apply_scaling(df, scale)
            if scale != 1 and "Close_gbp" in df.columns:
                df["Close_gbp"] = pd.to_numeric(df["Close_gbp"], errors="coerce") * scale

            # prefer GBP-close column if present
            close_col = None
            for col in ("Close_gbp", "Close", "close_gbp", "close"):
                if col in df.columns:
                    close_col = col
                    break
            if not close_col:
                continue

            df = df.sort_values(df.columns[0])  # first col is Date in your feeds
            last = df.iloc[-1]

            val = float(last[close_col])
            if not (val == val and val != float("inf") and val != float("-inf")):
                continue  # skip NaN/inf

            # store using the EXACT key your frontend expects
            key = f"{ticker}.{exchange}"
            result[key] = val

        except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
            # keep logging, but don't poison the map with zeros
            logger.warning("latest price fetch failed for %s: %s", full, e)

    logger.info("Latest prices fetched: %d/%d", len(result), len(full_tickers))
    return result


def load_live_prices(full_tickers: list[str]) -> dict[str, Dict[str, object]]:
    """Fetch real-time quotes for ``full_tickers``.

    Returns a mapping ``{'TICKER': {'price': float, 'timestamp': datetime}}``
    where the timestamp is timezone-aware (UTC). Entries with missing data are
    skipped. Any network or parsing errors result in an empty mapping.
    """

    out: dict[str, Dict[str, dt.datetime]] = {}
    if not full_tickers:
        return out

    symbols = ",".join(full_tickers)
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols}"

    try:
        from backend.common.portfolio_utils import _fx_to_gbp  # type: ignore

        fx_cache: Dict[str, float] = {}
        resp = requests.get(url, timeout=5)
        payload = resp.json().get("quoteResponse", {}).get("result", [])
        for row in payload:
            sym = row.get("symbol")
            price = row.get("regularMarketPrice")
            ts = row.get("regularMarketTime")
            if sym and price is not None and ts:
                price = float(price)

                # Apply scaling override (e.g., GBX -> GBP)
                tkr, exch = (sym.split(".", 1) + [""])[:2]
                scale = get_scaling_override(tkr, exch, None)
                price *= scale

                # Convert to GBP using latest FX rates if necessary
                meta = get_instrument_meta(sym)
                ccy = (meta.get("currency") or "GBP").upper()
                if ccy != "GBP":
                    price *= _fx_to_gbp(ccy, fx_cache)

                out[sym.upper()] = {
                    "price": price,
                    "timestamp": dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc),
                }
    except Exception as exc:
        logger.warning("live price fetch failed for %s: %s", symbols, exc)

    return out


# In-memory map populated elsewhere; exported for consumers that rely on it.
latest_prices: Dict[str, float] = {}


def _close_column(df: pd.DataFrame) -> Optional[str]:
    """
    Prefer GBP close if present, else fall back to Close or Adj Close,
    case-insensitive.
    """
    nm = _lower_name_map(df)
    return nm.get("close_gbp") or nm.get("close") or nm.get("adj close") or nm.get("adj_close")


# ─────── cost basis (single source of truth) ───────
def _derived_cost_basis_close_px(ticker: str, exchange: str, acq: dt.date, cache: dict[str, float]) -> Optional[float]:
    """
    Find a scaled close price near acquisition date (±2 weekdays). Cached by key.
    """
    start = _nearest_weekday(acq - dt.timedelta(days=2), False)
    end = _nearest_weekday(acq + dt.timedelta(days=2), True)
    key = f"{ticker}.{exchange}_{acq}"
    if key in cache:
        return cache[key]

    df = load_meta_timeseries_range(ticker, exchange, start_date=start, end_date=end)
    if df is None or df.empty:
        return None

    # apply scaling override
    scale = get_scaling_override(ticker, exchange, None)
    df = apply_scaling(df, scale)

    col = _close_column(df)
    if not col or df[col].empty:
        return None

    px = float(df[col].iloc[0])
    cache[key] = px
    return px


def _get_price_for_date_scaled(
    ticker: str,
    exchange: str,
    d: dt.date,
    field: str = "Close_gbp",
) -> tuple[Optional[float], Optional[str]]:
    if ticker.upper() in {"CASH", "GBP.CASH", "CASH.GBP"}:
        return 1.0, None

    """
    Load a single-day DF, apply scaling override and return the requested
    field together with its source. For close prices we prefer the
    GBP-converted column when available, falling back to the regular close.
    """
    df = load_meta_timeseries_range(ticker=ticker, exchange=exchange, start_date=d, end_date=d)
    if df is None or df.empty:
        return None, None

    scale = get_scaling_override(ticker, exchange, None)
    df = apply_scaling(df, scale)

    nm = _lower_name_map(df)
    col = None
    if field.lower() in {"close", "close_gbp"}:
        col = nm.get("close_gbp") or nm.get("close") or nm.get("adj close") or nm.get("adj_close")
    else:
        col = nm.get(field.lower())
    if not col or df.empty:
        return None, None

    try:
        price = float(df.iloc[0][col])
    except (ValueError, TypeError, KeyError, IndexError):
        return None, None

    src = df.iloc[0].get("Source")
    if pd.isna(src):
        src = None
    return price, src


def get_effective_cost_basis_gbp(
    h: Dict[str, Any],
    price_cache: dict[str, float],
) -> float:
    """
    If booked cost exists, use it. Otherwise derive:
      units * (close near acquisition OR latest cache price).
    """
    units = float(h.get(UNITS) or 0.0)
    if units <= 0:
        return 0.0

    booked_raw = h.get(COST_BASIS_GBP)
    try:
        booked = float(booked_raw) if booked_raw is not None else 0.0
    except (TypeError, ValueError):
        booked = 0.0
    if booked > 0:
        return round(booked, 2)

    from backend.common import instrument_api

    full = (h.get(TICKER) or "").upper()
    parts = full.split(".", 1)
    ticker = parts[0]
    resolved = instrument_api._resolve_full_ticker(full, price_cache)
    if resolved:
        ticker, exchange = resolved
    else:
        exchange = "L"
        logger.debug("Could not resolve exchange for %s; defaulting to L", full)
    acq = _parse_date(h.get(ACQUIRED_DATE))

    close_px = None
    if acq:
        close_px = _derived_cost_basis_close_px(ticker, exchange, acq, price_cache)
    if close_px is None:
        # last resort (already expected to be in *pounds* if you write it that way)
        close_px = price_cache.get(full)

    if close_px is None:
        return 0.0

    return round(units * float(close_px), 2)


# ───────────── canonical enrichment ─────────────
def enrich_holding(
    h: Dict[str, Any],
    today: dt.date,
    price_cache: dict[str, float],
    approvals: dict[str, dt.date] | None = None,
    user_config: UserConfig | None = None,
) -> Dict[str, Any]:
    """
    Canonical enrichment used by both owner and group builders.
    Produces the same keys in both paths.
    """
    out = dict(h)  # do not mutate caller
    full = (out.get(TICKER) or "").upper()
    meta = get_instrument_meta(full)
    ucfg = user_config or UserConfig(
        hold_days_min=config.hold_days_min,
        approval_exempt_types=config.approval_exempt_types,
        approval_exempt_tickers=config.approval_exempt_tickers,
    )

    account_ccy = (h.get("currency") or "GBP").upper()
    from backend.common.portfolio_utils import get_security_meta  # local import to avoid circular

    sec_meta = get_security_meta(full) or {}
    instr_meta = meta or {}
    # Merge metadata giving precedence to instrument files over
    # security metadata derived from portfolios. Previously the merge
    # order overwrote detailed instrument information (like the name)
    # with generic placeholders from security metadata, causing
    # instrument names to appear as tickers on the group page.
    meta = {**sec_meta, **instr_meta}

    if _is_cash(full, account_ccy):
        units = float(out.get(UNITS, 0) or 0.0)
        out["name"] = out.get("name") or _cash_name(full, account_ccy)
        out["currency"] = meta.get("currency") or account_ccy
        out["instrument_type"] = (
            meta.get("instrumentType") or meta.get("instrument_type") or "Cash"
        )
        out["sector"] = out.get("sector") or meta.get("sector")
        out["region"] = out.get("region") or meta.get("region")

        # price is 1.0 in account currency
        out["price"] = 1.0
        out["current_price_gbp"] = 1.0 if account_ccy == "GBP" else None  # keep simple; add FX later

        # book cost = value = units; gain = 0
        out["market_value_gbp"] = units if account_ccy == "GBP" else None
        out["gain_gbp"] = 0.0
        out["unrealised_gain_gbp"] = 0.0
        out["unrealized_gain_gbp"] = 0.0
        out["gain_pct"] = 0.0
        out["day_change_gbp"] = 0.0

        # cost basis fields
        out.setdefault(COST_BASIS_GBP, units if account_ccy == "GBP" else None)
        out[EFFECTIVE_COST_BASIS_GBP] = out[COST_BASIS_GBP]

        # eligibility not meaningful for cash
        out["days_held"] = None
        out["sell_eligible"] = True
        out["eligible_on"] = None
        out["days_until_eligible"] = 0
        out["next_eligible_sell_date"] = None
        out["cost_basis_source"] = "cash"

        return out

    from backend.common import instrument_api

    parts = full.split(".", 1)
    ticker = parts[0]
    resolved = instrument_api._resolve_full_ticker(full, price_cache)
    if resolved:
        ticker, exchange = resolved
    else:
        exchange = "L"
        logger.debug("Could not resolve exchange for %s; defaulting to L", full)

    out["currency"] = meta.get("currency")
    out["instrument_type"] = meta.get("instrumentType") or meta.get("instrument_type")
    out["name"] = out.get("name") or meta.get("name") or full
    out["sector"] = out.get("sector") or meta.get("sector")
    out["region"] = out.get("region") or meta.get("region")
    out["asset_class"] = (
        out.get("asset_class")
        or meta.get("assetClass")
        or meta.get("asset_class")
    )

    units = float(out.get(UNITS, 0) or 0.0)
    if units <= 0:
        out.setdefault(COST_BASIS_GBP, None)
        out[EFFECTIVE_COST_BASIS_GBP] = 0.0
        out["market_value_gbp"] = 0.0
        out["gain_gbp"] = 0.0
        out["unrealised_gain_gbp"] = 0.0
        out["unrealized_gain_gbp"] = 0.0
        out["gain_pct"] = None
        out["day_change_gbp"] = 0.0
        out["days_held"] = None
        out["sell_eligible"] = False
        out["eligible_on"] = None
        out["days_until_eligible"] = None
        out["next_eligible_sell_date"] = None
        out["price"] = None
        out["current_price_gbp"] = None
        out["cost_basis_source"] = "none"
        return out

    # default acquired date if missing
    if out.get(ACQUIRED_DATE) is None:
        out[ACQUIRED_DATE] = (today - dt.timedelta(days=365)).isoformat()

    acq = _parse_date(out.get(ACQUIRED_DATE))
    if acq:
        days = (today - acq).days
        out["days_held"] = days
        hold_days = ucfg.hold_days_min or 0
        eligible = days >= hold_days
        next_date = acq + dt.timedelta(days=hold_days)
        out["eligible_on"] = next_date.isoformat()
        out["next_eligible_sell_date"] = next_date.isoformat()
        out["days_until_eligible"] = max(0, hold_days - days)
    else:
        out["days_held"] = None
        eligible = False
        out["eligible_on"] = None
        out["days_until_eligible"] = None
        out["next_eligible_sell_date"] = None

    instr_type = (meta.get("instrumentType") or meta.get("instrument_type") or "").upper()
    asset_class = (
        meta.get("assetClass") or meta.get("asset_class") or ""
    ).upper()
    sector = (meta.get("sector") or "").upper()
    is_commodity = asset_class == "COMMODITY" or sector == "COMMODITY"
    is_etf = instr_type == "ETF"
    exempt_tickers = {t.upper() for t in (ucfg.approval_exempt_tickers or [])}
    exempt_types = {t.upper() for t in (ucfg.approval_exempt_types or [])}
    exempt_type = instr_type in exempt_types
    if is_etf and is_commodity:
        exempt_type = False
    needs_approval = not (
        ticker.upper() in exempt_tickers
        or full.upper() in exempt_tickers
        or exempt_type
    )
    approved = False
    if approvals and needs_approval:
        approved_on = approvals.get(full.upper()) or approvals.get(ticker.upper())
        if approved_on:
            approved = is_approval_valid(approved_on, today)

    out["sell_eligible"] = bool(eligible and (approved or not needs_approval))

    # Effective cost basis (always computed)
    ecb = get_effective_cost_basis_gbp(out, price_cache)
    out[EFFECTIVE_COST_BASIS_GBP] = ecb

    # Choose cost for gains: prefer booked cost if present, else effective
    cost_for_gain = float(out.get(EFFECTIVE_COST_BASIS_GBP) or 0.0) or ecb

    units = float(out.get(UNITS, 0) or 0)

    px = px_source = prev_px = None
    last_price_time = None
    is_stale = True
    if units != 0:
        from backend.common import portfolio_utils as pu  # local import to avoid circular

        snap = pu._PRICE_SNAPSHOT.get(full) or pu._PRICE_SNAPSHOT.get(ticker)
        if isinstance(snap, dict) and snap.get("last_price") is not None:
            px = float(snap["last_price"])
            last_price_time = snap.get("last_price_time")
            is_stale = bool(snap.get("is_stale", False))
            px_source = "snapshot"
            prev_date = _nearest_weekday(today - dt.timedelta(days=1), forward=False)
        else:
            # fallback to previous close
            asof_date = today - dt.timedelta(days=1)
            px, px_source = _get_price_for_date_scaled(
                ticker, exchange, asof_date, field="Close_gbp"
            )
            prev_date = _nearest_weekday(asof_date - dt.timedelta(days=1), forward=False)

        prev_px, _ = _get_price_for_date_scaled(
            ticker, exchange, prev_date, field="Close_gbp"
        )

    out["price"] = px  # legacy name used in parts of UI
    out["current_price_gbp"] = px
    out["latest_source"] = px_source
    out["last_price_time"] = last_price_time
    out["is_stale"] = is_stale

    if px is not None:
        mv = round(units * float(px), 2)
        out["market_value_gbp"] = mv
        out["gain_gbp"] = round(mv - cost_for_gain, 2)

        # aliases for UI compatibility (UK + US)
        out["unrealised_gain_gbp"] = out["gain_gbp"]
        out["unrealized_gain_gbp"] = out["gain_gbp"]

        # percentage gain
        out["gain_pct"] = ((mv - cost_for_gain) / cost_for_gain * 100.0) if cost_for_gain > 0 else None
    else:
        out["market_value_gbp"] = None
        out["gain_gbp"] = None
        out["unrealised_gain_gbp"] = None  # keep both spellings
        out["unrealized_gain_gbp"] = None
        out["gain_pct"] = None

    if px is not None and prev_px is not None:
        change_val = (px - prev_px) * units
        out["day_change_gbp"] = round(change_val, 2)
    else:
        out["day_change_gbp"] = None

    # provenance
    out["cost_basis_source"] = "book" if float(out.get(COST_BASIS_GBP) or 0.0) > 0 else "derived"

    return out


# top-level helper
def _is_cash(full: str, account_ccy: str = "GBP") -> bool:
    f = (full or "").upper()
    # allow several spellings
    return f in {f"CASH.{account_ccy}", f"{account_ccy}.CASH", "CASH"}


def _cash_name(full: str, account_ccy: str = "GBP") -> str:
    return f"Cash ({account_ccy})"
