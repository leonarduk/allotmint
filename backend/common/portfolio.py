"""
Owner-level portfolio builder for AllotMint
==========================================

• build_owner_portfolio(owner)
• list_owners()
• enrich_position()              – helper reused by group_portfolio
"""

from __future__ import annotations

import csv
import datetime as dt
import importlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.common.data_loader import list_plots, load_account
from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries

MAX_TRADES_PER_MONTH = 20
HOLD_DAYS_MIN        = 30

_REPO_ROOT   = Path(__file__).resolve().parents[2]
_PLOTS_ROOT  = _REPO_ROOT / "data" / "accounts"
_PRICES_JSON = _REPO_ROOT / "data" / "prices" / "latest_prices.json"

# ─────────────────────── trades helpers (restored) ──────────────────────
def _local_trades_path(owner: str) -> Path:
    return _PLOTS_ROOT / owner / "trades.csv"

def _load_trades_local(owner: str) -> List[Dict[str, Any]]:
    path = _local_trades_path(owner)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def _load_trades_aws(owner: str) -> List[Dict[str, Any]]:
    # TODO: implement S3 lookup once infra in place
    return []

def load_trades(owner: str, env: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Public helper used by portfolio_loader and others.
    Keeps us self-contained so there’s no circular dependency.
    """
    env = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    return _load_trades_local(owner) if env == "local" else _load_trades_aws(owner)

# ─────────────────────────── generic helpers ───────────────────────────
def _parse_date(s: str) -> Optional[dt.date]:
    try: return dt.datetime.fromisoformat(s).date()
    except Exception: return None

def _nearest_weekday(d: dt.date, forward: bool) -> dt.date:
    while d.weekday() >= 5:
        d += dt.timedelta(days=1 if forward else -1)
    return d

def _maybe_get_price_gbp(ticker: str) -> float | None:
    """Avoid circular import with backend.common.prices."""
    try:
        mod = importlib.import_module("backend.common.prices")
        return getattr(mod, "get_price_gbp")(ticker)
    except Exception:
        return None

def load_latest_prices(path: Path = _PRICES_JSON) -> Dict[str, float]:
    try:
        with path.open(encoding="utf-8") as f:
            return {k.upper(): float(v) for k, v in json.load(f).items()}
    except Exception:
        return {}

# ───────────────── cost-basis logic (single source of truth) ───────────
def get_effective_cost_basis(h: Dict[str, Any],
                             cache: dict,
                             latest: dict[str, float]) -> float:
    """Book cost →  ±2-day close → cached JSON → live quote."""
    if (cb := h.get("cost_basis_gbp", 0)) > 0:
        return cb

    full = h["ticker"];  ticker, exchange = (full.split(".", 1) + ["L"])[:2]
    try:
        acq = dt.datetime.fromisoformat(h["acquired_date"]).date()
    except Exception:
        acq = None

    close_px: float | None = None
    if acq:
        start = _nearest_weekday(acq - dt.timedelta(days=2), False)
        end   = _nearest_weekday(acq + dt.timedelta(days=2), True)
        key   = f"{ticker}.{exchange}_{acq}"
        if key in cache:
            close_px = cache[key]
        else:
            df = fetch_meta_timeseries(ticker, exchange, start_date=start, end_date=end)
            if df is not None and not df.empty:
                if "close" not in df.columns and "Close" in df.columns:
                    df = df.rename(columns={"Close": "close"})
                if "close" in df.columns:
                    close_px = float(df["close"].iloc[0])
                    cache[key] = close_px

    if close_px is None:
        close_px = latest.get(full.upper()) or _maybe_get_price_gbp(full.upper())

    if close_px is None:
        return 0.0

    return round(float(h.get("units", 0)) * close_px, 2)

# ─────────────── reusable per-holding enrichment helper ────────────────
def enrich_position(h: Dict[str, Any],
                    today: dt.date,
                    price_cache: dict,
                    latest_prices: dict[str, float]) -> Dict[str, Any]:
    """Return a fully enriched holding dict (cost, gain, eligibility, etc.)."""
    out = dict(h)

    # days-held & eligibility
    if (acq := _parse_date(out.get("acquired_date", ""))):
        days = (today - acq).days
        out |= {
            "days_held": days,
            "sell_eligible":   days >= HOLD_DAYS_MIN,
            "eligible_on":     (acq + dt.timedelta(days=HOLD_DAYS_MIN)).isoformat(),
            "days_until_eligible": max(0, HOLD_DAYS_MIN - days),
        }
    else:
        out |= {"days_held": None, "sell_eligible": False,
                "eligible_on": None, "days_until_eligible": None}

    # cost basis
    out["effective_cost_basis_gbp"] = get_effective_cost_basis(
        out, price_cache, latest_prices
    )

    # current price & gains
    tkr   = out["ticker"].upper()
    units = float(out.get("units", 0) or 0)
    price = latest_prices.get(tkr) or _maybe_get_price_gbp(tkr)
    out["current_price_gbp"] = price

    if price is not None:
        mv = round(units * price, 2)
        out["market_value_gbp"]   = mv
        out["gain_gbp"]           = round(mv - out["effective_cost_basis_gbp"], 2)
        out["unrealized_gain_gbp"] = out["gain_gbp"]
    else:
        out["market_value_gbp"]   = None
        out["gain_gbp"]           = None
        out["unrealized_gain_gbp"] = None

    return out

# ─────────────────────── owner-level builder ───────────────────────────
def build_owner_portfolio(owner: str, env: Optional[str] = None) -> Dict[str, Any]:
    env    = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    today  = dt.date.today()
    plots  = [p for p in list_plots(env=env) if p["owner"] == owner]
    if not plots:
        raise FileNotFoundError(f"No plot for owner '{owner}'")
    accounts_meta = plots[0]["accounts"]

    trades = load_trades(owner, env=env)
    trades_this = sum(1 for t in trades if _parse_date(t.get("date", "")).month == today.month)
    trades_rem  = max(0, MAX_TRADES_PER_MONTH - trades_this)

    latest_prices = load_latest_prices()
    price_cache: dict[str, float] = {}
    accounts: List[Dict[str, Any]] = []

    for meta in accounts_meta:
        raw   = load_account(owner, meta, env=env)
        holdings_raw = raw.get("holdings", [])
        hold = [enrich_position(h, today, price_cache, latest_prices)
                for h in holdings_raw]
        val_gbp = sum(h["market_value_gbp"] or 0 for h in hold)
        accounts.append({
            "account_type": raw.get("account_type", meta.upper()),
            "currency":     raw.get("currency", "GBP"),
            "last_updated": raw.get("last_updated"),
            "value_estimate_gbp": val_gbp,
            "holdings": hold,
        })

    return {
        "owner": owner,
        "as_of": today.isoformat(),
        "trades_this_month": trades_this,
        "trades_remaining":  trades_rem,
        "accounts": accounts,
        "total_value_estimate_gbp": sum(a["value_estimate_gbp"] for a in accounts),
    }

# ─────────────────────── owners utility ────────────────────────────────
def list_owners() -> list[str]:
    owners = []
    for pf in _PLOTS_ROOT.glob("*/person.json"):
        try:
            if slug := json.loads(pf.read_text()).get("owner") or json.loads(pf.read_text()).get("slug"):
                owners.append(slug)
        except Exception:
            continue
    return owners
