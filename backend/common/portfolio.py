from __future__ import annotations

"""
Derived portfolio utilities for AllotMint.

Computes:
- days_held
- sell_eligible (>=30 days)
- eligible_on
- trades_this_month / trades_remaining

Market prices are placeholder None for now.
"""

import csv
import datetime as dt
import os
import pathlib
from typing import Any, Dict, List, Optional

from backend.common.data_loader import list_plots, load_account
from backend.common.prices import get_price_gbp, load_securities
from backend.common.pension import _age_from_dob, estimate_db_pension_value

MAX_TRADES_PER_MONTH = 20
HOLD_DAYS_MIN = 30

# Re-resolve local data root (repeat logic here so we don't depend on private symbol)
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_LOCAL_PLOTS_ROOT = _REPO_ROOT / "data-sample" / "plots"


# ---------- trades ----------------------------------------------------------

def _local_trades_path(owner: str) -> pathlib.Path:
    return _LOCAL_PLOTS_ROOT / owner / "trades.csv"


def _load_trades_local(owner: str) -> List[Dict[str, Any]]:
    path = _local_trades_path(owner)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        return list(rdr)


def _load_trades_aws(owner: str) -> List[Dict[str, Any]]:
    # TODO: implement S3 lookup once infra in place
    return []


def load_trades(owner: str, env: Optional[str] = None) -> List[Dict[str, Any]]:
    env = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    return _load_trades_local(owner) if env == "local" else _load_trades_aws(owner)


# ---------- helpers ---------------------------------------------------------

def _parse_date(date_str: str) -> Optional[dt.date]:
    try:
        # handles full ISO string with time
        return dt.datetime.fromisoformat(date_str).date()
    except Exception:
        return None


def count_trades_this_month(trades: List[Dict[str, Any]], today: dt.date) -> int:
    count = 0
    for t in trades:
        d = _parse_date(t.get("date", ""))
        if d and d.year == today.year and d.month == today.month:
            act = (t.get("action") or "").upper()
            if act in ("BUY", "SELL"):
                count += 1
    return count


def enrich_holding(h: Dict[str, Any], today: dt.date) -> Dict[str, Any]:
    out = dict(h)
    acq = _parse_date(str(h.get("acquired_date", "")))
    if acq:
        days_held = (today - acq).days
        eligible_on = acq + dt.timedelta(days=HOLD_DAYS_MIN)
        out["days_held"] = days_held
        out["sell_eligible"] = days_held >= HOLD_DAYS_MIN
        out["eligible_on"] = eligible_on.isoformat()
        out["days_until_eligible"] = max(0, HOLD_DAYS_MIN - days_held)
    else:
        out["days_held"] = None
        out["sell_eligible"] = False
        out["eligible_on"] = None
        out["days_until_eligible"] = None

    out.setdefault("current_price_gbp", None)
    out.setdefault("market_value_gbp", None)
    return out


# ---------- portfolio builder -----------------------------------------------

def build_owner_portfolio(owner: str, env: Optional[str] = None) -> Dict[str, Any]:
    env = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    today = dt.date.today()

    # Discover which accounts exist for this owner
    plot_list = [p for p in list_plots(env=env) if p["owner"] == owner]
    if not plot_list:
        raise FileNotFoundError(f"No plot for owner '{owner}'")
    accounts = plot_list[0]["accounts"]

    # Load trades & compliance counters
    trades = load_trades(owner, env=env)
    trades_this_month = count_trades_this_month(trades, today)
    trades_remaining = max(0, MAX_TRADES_PER_MONTH - trades_this_month)

    # Load security metadata (not strictly needed yet, but handy)
    secs_map = load_securities(env=env)  # ticker->SecMeta

    acct_objs: List[Dict[str, Any]] = []

    for acct in accounts:
        raw = load_account(owner, acct, env=env)

        # Some (e.g. pension-forecast) may not have holdings[]
        holdings_raw = raw.get("holdings", [])

        holdings = []
        acct_value = 0.0

        for h in holdings_raw:
            h_en = enrich_holding(h, today)
            tkr = h.get("ticker")
            units = float(h.get("units", 0) or 0)

            # price lookup (falls back to None)
            price_gbp = get_price_gbp(tkr, env=env)
            h_en["current_price_gbp"] = price_gbp

            if price_gbp is not None:
                mv = units * price_gbp
            else:
                # fall back to cost basis if no price
                mv = float(h.get("cost_basis_gbp", 0) or 0)

            h_en["market_value_gbp"] = mv
            acct_value += mv

            # unrealized gain
            cost = float(h.get("cost_basis_gbp", 0) or 0)
            h_en["unrealized_gain_gbp"] = mv - cost

            holdings.append(h_en)

        # ←← THIS IS WHERE THE append() GOES (inside the acct loop)
        acct_objs.append({
            "account_type": raw.get("account_type", acct.upper()),
            "currency": raw.get("currency", "GBP"),
            "last_updated": raw.get("last_updated"),
            "value_estimate_gbp": acct_value,
            "holdings": holdings,
        })

    # after all accounts processed
    total_value = sum(a["value_estimate_gbp"] for a in acct_objs)

    return {
        "owner": owner,
        "as_of": today.isoformat(),
        "trades_this_month": trades_this_month,
        "trades_remaining": trades_remaining,
        "accounts": acct_objs,
        "total_value_estimate_gbp": total_value,
    }
