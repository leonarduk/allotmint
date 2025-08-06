"""
Group-level portfolio utilities for AllotMint
=============================================
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, DefaultDict, Optional

from backend.common.portfolio import (
    build_owner_portfolio,
    enrich_position,
    load_latest_prices,
)
logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = _REPO_ROOT / "data"
GROUPS_FILE = DATA_ROOT / "groups.json"
PLOTS_ROOT = DATA_ROOT / "accounts"
TODAY = dt.date.today()


# ───────────────── group definitions ──────────────────────────
def _auto_groups() -> List[Dict[str, Any]]:
    adults, children, everyone = [], [], []
    for pf in PLOTS_ROOT.glob("*/person.json"):
        try:
            info = json.loads(pf.read_text())
            slug = info.get("owner") or info.get("slug")
            dob = info.get("dob") or info.get("birth_date")
            age = None
            if dob:
                age = (TODAY - dt.datetime.fromisoformat(dob).date()).days // 365
            if slug and age is not None:
                everyone.append(slug)
                (children if age < 18 else adults).append(slug)
        except Exception:
            continue
    return [
        {"slug": "children", "name": "Children", "members": children},
        {"slug": "adults", "name": "Adults", "members": adults},
        {"slug": "all", "name": "All", "members": everyone},
    ]


def list_groups() -> List[Dict[str, Any]]:
    return json.loads(GROUPS_FILE.read_text()) if GROUPS_FILE.exists() else _auto_groups()


# ───────────────────────── builder ────────────────────────────
def build_group_portfolio(slug: str, env: Optional[str] = None) -> Dict[str, Any]:
    env = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    today_iso = TODAY.isoformat()
    slug = slug.lower()  # <- ensure consistent matching
    all_groups = list_groups()
    grp = next((g for g in all_groups if g["slug"].lower() == slug), None)

    if not grp:
        raise KeyError(f"No group with slug '{slug}'")

    latest_prices = load_latest_prices()
    price_cache: dict[str, float] = {}
    past_cache: dict[str, float] = {}

    owner_ps = [build_owner_portfolio(m, env=env) for m in grp["members"]]

    acct_map: DefaultDict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "account_type": "",
            "currency": "GBP",
            "last_updated": today_iso,
            "value_estimate_gbp": 0.0,
            "holdings": [],
        }
    )
    trades_this = trades_rem = 0
    instrument_totals: DefaultDict[str, Dict[str, Any]] = defaultdict(
        lambda: {"ticker": "", "name": "", "units": 0.0, "value": 0.0, "cost": 0.0}
    )

    # Relative dates
    delta_map = {
        "1d": TODAY - dt.timedelta(days=1),
        "7d": TODAY - dt.timedelta(days=7),
        "1mo": TODAY - dt.timedelta(days=30),
        "1yr": TODAY - dt.timedelta(days=365),
    }

    for op in owner_ps:
        trades_this += op["trades_this_month"]
        trades_rem += op["trades_remaining"]
        for acct in op["accounts"]:
            ga = acct_map[acct["account_type"]]
            ga["account_type"] = acct["account_type"]
            ga["currency"] = acct["currency"]
            ga["value_estimate_gbp"] += acct["value_estimate_gbp"]

            for h in acct.get("holdings", []):
                full_ticker = h.get("ticker", "").strip()

                if not full_ticker:
                    logger.warning(f"Skipping holding with missing ticker in account: {acct['account_type']}")
                    continue

                if h.get("effective_cost_basis_gbp", 0) == 0:
                    h = enrich_position(h, TODAY, price_cache, latest_prices)

                ga["holdings"].append(h)

                instr = instrument_totals[full_ticker]
                instr["ticker"] = full_ticker
                instr["name"] = h.get("name", "")
                instr["units"] += h.get("units", 0)
                instr["value"] += h.get("market_value_gbp") or 0
                instr["cost"] += (
                    h.get("cost_basis_gbp")
                    or h.get("effective_cost_basis_gbp")
                    or 0
                )

                # Rolling gains
                for label, past_date in delta_map.items():
                    past_price = fetch_cached_price(full_ticker, past_cache, latest_prices)
                    latest_price = latest_prices.get(full_ticker, {}).get("latest_price", 0.0)
                    gain = h.get("units", 0) * (latest_price - past_price)
                    instr[f"gain_{label}"] = instr.get(f"gain_{label}", 0) + gain

    accounts = list(acct_map.values())
    return {
        "group": slug,
        "name": grp["name"],
        "members": grp["members"],
        "as_of": today_iso,
        "trades_this_month": trades_this,
        "trades_remaining": trades_rem,
        "accounts": accounts,
        "instrument_totals": list(instrument_totals.values()),
        "total_value_estimate_gbp": sum(a["value_estimate_gbp"] for a in accounts),
    }


def fetch_cached_price(ticker: str, cache: dict[str, float], latest_prices: dict[str, Any]) -> float:
    if ticker in cache:
        return cache[ticker]
    p = latest_prices.get(ticker, {})
    val = p.get("latest_price", 0.0)
    cache[ticker] = val
    return val
