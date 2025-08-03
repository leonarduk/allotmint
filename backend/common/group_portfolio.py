"""
Group-level portfolio utilities for AllotMint
============================================
"""

from __future__ import annotations
import datetime as dt, json, os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, DefaultDict, Optional

from backend.common.portfolio import (
    build_owner_portfolio,
    enrich_position,           # ← reuse helper
    load_latest_prices,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT  = _REPO_ROOT / "data"
GROUPS_FILE = DATA_ROOT / "groups.json"
PLOTS_ROOT  = DATA_ROOT / "accounts"
TODAY = dt.date.today()

# ───────────────── group definitions ──────────────────────────
def _auto_groups() -> List[Dict[str, Any]]:
    adults, children, everyone = [], [], []
    for pf in PLOTS_ROOT.glob("*/person.json"):
        try:
            info = json.loads(pf.read_text()); slug = info.get("owner") or info.get("slug")
            dob  = info.get("dob") or info.get("birth_date")
            age  = None
            if dob:
                age = (TODAY - dt.datetime.fromisoformat(dob).date()).days // 365
            if slug and age is not None:
                everyone.append(slug)
                (children if age < 18 else adults).append(slug)
        except Exception:
            continue
    return [
        {"slug": "children", "name": "Children", "members": children},
        {"slug": "adults",   "name": "Adults",   "members": adults},
        {"slug": "all",      "name": "All",      "members": everyone},
    ]

def list_groups() -> List[Dict[str, Any]]:
    return json.loads(GROUPS_FILE.read_text()) if GROUPS_FILE.exists() else _auto_groups()

# ───────────────────────── builder ────────────────────────────
def build_group_portfolio(slug: str, env: Optional[str] = None) -> Dict[str, Any]:
    env    = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    today_iso = TODAY.isoformat()
    grp   = next(g for g in list_groups() if g["slug"] == slug)
    latest_prices = load_latest_prices()
    price_cache: dict[str, float] = {}

    owner_ps = [build_owner_portfolio(m, env=env) for m in grp["members"]]

    acct_map: DefaultDict[str, Dict[str, Any]] = defaultdict(
        lambda: {"account_type": "", "currency": "GBP",
                 "last_updated": today_iso, "value_estimate_gbp": 0.0, "holdings": []}
    )
    trades_this = trades_rem = 0

    for op in owner_ps:
        trades_this += op["trades_this_month"];  trades_rem += op["trades_remaining"]
        for acct in op["accounts"]:
            ga = acct_map[acct["account_type"]]
            ga["account_type"] = acct["account_type"];  ga["currency"] = acct["currency"]
            ga["value_estimate_gbp"] += acct["value_estimate_gbp"]

            # ensure each holding carries effective cost (already enriched, but be safe)
            for h in acct.get("holdings", []):
                if h.get("effective_cost_basis_gbp", 0) == 0:
                    h = enrich_position(h, TODAY, price_cache, latest_prices)
                ga["holdings"].append(h)

    accounts = list(acct_map.values())
    return {
        "group": slug, "name": grp["name"], "members": grp["members"], "as_of": today_iso,
        "trades_this_month": trades_this, "trades_remaining": trades_rem,
        "accounts": accounts,
        "total_value_estimate_gbp": sum(a["value_estimate_gbp"] for a in accounts),
    }
