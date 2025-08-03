"""
Group-level portfolio utilities for AllotMint
============================================

• list_groups()            – return group definitions
• build_group_portfolio()  – aggregate owner portfolios for one group
"""

from __future__ import annotations

import datetime as dt
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, DefaultDict

from backend.timeseries.fetch_meta_timeseries import fetch_meta_timeseries
from backend.common.portfolio import load_latest_prices   # ← reuse helper

# ───────────────────────────────────────────────────────────────
# File locations
# ───────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT  = _REPO_ROOT / "data"
GROUPS_FILE = DATA_ROOT / "groups.json"
PLOTS_ROOT  = DATA_ROOT / "accounts"

TODAY = dt.date.today()

# ───────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────
def _derive_age(info: dict) -> int | None:
    if "age" in info:
        try: return int(info["age"])
        except Exception: return None
    if dob := info.get("dob") or info.get("birth_date"):
        try:
            return (TODAY - dt.datetime.fromisoformat(dob).date()).days // 365
        except Exception:
            return None
    return None

def _auto_groups_from_person_json() -> List[Dict[str, Any]]:
    adults, children, everyone = [], [], []
    for pf in PLOTS_ROOT.glob("*/person.json"):
        try:
            info = json.loads(pf.read_text())
        except Exception:
            continue
        slug = info.get("owner") or info.get("slug")
        age  = _derive_age(info)
        if slug and age is not None:
            everyone.append(slug)
            (children if age < 18 else adults).append(slug)
    return [
        {"slug": "children", "name": "Children", "members": children},
        {"slug": "adults",   "name": "Adults",   "members": adults},
        {"slug": "all",      "name": "All",      "members": everyone},
    ]

def list_groups() -> List[Dict[str, Any]]:
    if GROUPS_FILE.exists():
        return json.loads(GROUPS_FILE.read_text())
    if not PLOTS_ROOT.exists():
        raise FileNotFoundError("data/groups.json not found and no account dirs present")
    return _auto_groups_from_person_json()

# ───────────────────────────────────────────────────────────────
# Cost-basis helper (same logic as owner-level version)
# ───────────────────────────────────────────────────────────────
def _wkday(d: dt.date, fwd: bool) -> dt.date:
    while d.weekday() >= 5:
        d += dt.timedelta(days=1 if fwd else -1)
    return d

def get_effective_cost_basis(h: Dict[str, Any],
                             cache: dict,
                             latest: dict[str, float]) -> float:
    if (cb := h.get("cost_basis_gbp", 0)) > 0:
        return cb

    full = h["ticker"]
    ticker, exchange = (full.split(".", 1) + ["L"])[:2]

    try:
        acquired = dt.datetime.fromisoformat(h["acquired_date"]).date()
    except Exception:
        acquired = None

    close_px: float | None = None
    if acquired:
        start = _wkday(acquired - dt.timedelta(days=2), False)
        end   = _wkday(acquired + dt.timedelta(days=2), True)
        key   = f"{ticker}.{exchange}_{acquired}"
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
        close_px = latest.get(full.upper())

    if close_px is None:
        return 0.0

    return round(float(h.get("units", 0)) * close_px, 2)

# ───────────────────────────────────────────────────────────────
# main builder
# ───────────────────────────────────────────────────────────────
def build_group_portfolio(slug: str, env: Optional[str] = None) -> Dict[str, Any]:
    from backend.common.portfolio import build_owner_portfolio  # lazy import

    env         = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    today_iso   = TODAY.isoformat()
    latest_prices = load_latest_prices()                         # ← cached JSON
    price_cache: dict[str, float] = {}

    grp      = next(g for g in list_groups() if g["slug"] == slug)
    members  = grp.get("members", [])
    owner_ps = [build_owner_portfolio(m, env=env) for m in members]

    acct_map: DefaultDict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "account_type": "",
            "currency": "GBP",
            "last_updated": today_iso,
            "value_estimate_gbp": 0.0,
            "holdings": [],
        }
    )
    trades_this_month = trades_remaining = 0

    for op in owner_ps:
        trades_this_month += op.get("trades_this_month", 0)
        trades_remaining  += op.get("trades_remaining", 0)

        for acct in op["accounts"]:
            a_type = acct.get("account_type", "").upper()
            g_acct = acct_map[a_type]
            g_acct["account_type"] = a_type
            g_acct["currency"]     = acct.get("currency", "GBP")
            g_acct["value_estimate_gbp"] += acct.get("value_estimate_gbp", 0.0)

            for h in acct["holdings"]:
                h["effective_cost_basis_gbp"] = get_effective_cost_basis(
                    h, price_cache, latest_prices
                )
                g_acct["holdings"].append(h)

    accounts = list(acct_map.values())
    total_val = sum(a["value_estimate_gbp"] for a in accounts)

    return {
        "group": slug.lower(),
        "name":  grp.get("name", slug.title()),
        "members": members,
        "as_of":   today_iso,
        "trades_this_month": trades_this_month,
        "trades_remaining":  trades_remaining,
        "accounts": accounts,
        "total_value_estimate_gbp": total_val,
    }
