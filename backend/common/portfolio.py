"""
Owner-level portfolio builder for AllotMint
==========================================

• build_owner_portfolio(owner) – main entry
• list_owners()               – returns all owner slugs

This version never hard-imports backend.common.prices at module load
time; instead it uses _maybe_get_price_gbp() so prices.py can safely
call build_owner_portfolio() while it is still initialising.
"""

from __future__ import annotations

import csv
import datetime as dt
import importlib
import json
import os
import pathlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.common.data_loader import list_plots, load_account

MAX_TRADES_PER_MONTH = 20
HOLD_DAYS_MIN = 30

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_LOCAL_PLOTS_ROOT = _REPO_ROOT / "data-sample" / "plots"


# ──────────────────────────────────────────────────────────────
# helper to avoid circular import with prices.py
# ──────────────────────────────────────────────────────────────
def _maybe_get_price_gbp(ticker: str) -> float | None:
    """
    Safely return latest GBP price for *ticker* if
    backend.common.prices is fully initialised.

    When build_owner_portfolio() is invoked DURING prices.py import,
    the module is still ‘partially initialised’; we catch that case
    and just return None (price unavailable).
    """
    try:
        prices_mod = importlib.import_module("backend.common.prices")
        return getattr(prices_mod, "get_price_gbp")(ticker)
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
# trades helpers
# ──────────────────────────────────────────────────────────────
def _local_trades_path(owner: str) -> pathlib.Path:
    return _LOCAL_PLOTS_ROOT / owner / "trades.csv"


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
    env = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    return _load_trades_local(owner) if env == "local" else _load_trades_aws(owner)


# ──────────────────────────────────────────────────────────────
# misc helpers
# ──────────────────────────────────────────────────────────────
def _parse_date(s: str) -> Optional[dt.date]:
    try:
        return dt.datetime.fromisoformat(s).date()
    except Exception:
        return None


def count_trades_this_month(trades: List[Dict[str, Any]], today: dt.date) -> int:
    return sum(
        1
        for t in trades
        if (d := _parse_date(t.get("date", "")))
        and d.year == today.year
        and d.month == today.month
        and (t.get("action") or "").upper() in ("BUY", "SELL")
    )


def enrich_holding(h: Dict[str, Any], today: dt.date) -> Dict[str, Any]:
    out = dict(h)
    acq = _parse_date(str(h.get("acquired_date", "")))
    if acq:
        days = (today - acq).days
        out.update(
            days_held=days,
            sell_eligible=days >= HOLD_DAYS_MIN,
            eligible_on=(acq + dt.timedelta(days=HOLD_DAYS_MIN)).isoformat(),
            days_until_eligible=max(0, HOLD_DAYS_MIN - days),
        )
    else:
        out.update(
            days_held=None,
            sell_eligible=False,
            eligible_on=None,
            days_until_eligible=None,
        )
    out.setdefault("current_price_gbp", None)
    out.setdefault("market_value_gbp", None)
    return out


# ──────────────────────────────────────────────────────────────
# main builder
# ──────────────────────────────────────────────────────────────
def build_owner_portfolio(owner: str, env: Optional[str] = None) -> Dict[str, Any]:
    env = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    today = dt.date.today()

    plots = [p for p in list_plots(env=env) if p["owner"] == owner]
    if not plots:
        raise FileNotFoundError(f"No plot for owner '{owner}'")
    accounts_meta = plots[0]["accounts"]

    trades = load_trades(owner, env=env)
    trades_this_month = count_trades_this_month(trades, today)
    trades_remaining = max(0, MAX_TRADES_PER_MONTH - trades_this_month)

    latest_prices = load_latest_prices()  # ✅ Load once

    acct_objs: List[Dict[str, Any]] = []

    for acct_meta in accounts_meta:
        raw = load_account(owner, acct_meta, env=env)
        holdings_raw = raw.get("holdings", [])

        holdings = []
        acct_value = 0.0

        for h in holdings_raw:
            h_en = enrich_holding(h, today)
            tkr = h.get("ticker")
            units = float(h.get("units", 0) or 0)

            price = latest_prices.get(tkr)  # ✅ Use latest price if present
            h_en["current_price_gbp"] = price

            mv = units * price if price is not None else float(h.get("cost_basis_gbp", 0) or 0)
            h_en["market_value_gbp"] = mv
            h_en["unrealized_gain_gbp"] = mv - float(h.get("cost_basis_gbp", 0) or 0)

            acct_value += mv
            holdings.append(h_en)

        acct_objs.append(
            {
                "account_type": raw.get("account_type", acct_meta.upper()),
                "currency": raw.get("currency", "GBP"),
                "last_updated": raw.get("last_updated"),
                "value_estimate_gbp": acct_value,
                "holdings": holdings,
            }
        )

    return {
        "owner": owner,
        "as_of": today.isoformat(),
        "trades_this_month": trades_this_month,
        "trades_remaining": trades_remaining,
        "accounts": acct_objs,
        "total_value_estimate_gbp": sum(a["value_estimate_gbp"] for a in acct_objs),
    }


# ──────────────────────────────────────────────────────────────
# owners utility (safe to import anywhere)
# ──────────────────────────────────────────────────────────────
def list_owners() -> list[str]:
    owners = []
    for person_file in _LOCAL_PLOTS_ROOT.glob("*/person.json"):
        try:
            info = json.loads(person_file.read_text())
            if slug := info.get("owner") or info.get("slug"):
                owners.append(slug)
        except Exception:
            continue
    return owners

def load_latest_prices(path="data/prices/latest_prices.json") -> Dict[str, float]:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}
