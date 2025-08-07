from __future__ import annotations

from datetime import datetime, timedelta

from backend.timeseries.cache import load_meta_timeseries_range

MARKET_VALUE_GBP = "market_value_gbp"

EFFECTIVE_COST_BASIS_GBP = "effective_cost_basis_gbp"

COST_BASIS_GBP = "cost_basis_gbp"

ACQUIRED_DATE = "acquired_date"

GAIN_GBP = "gain_gbp"

DAYS_HELD = "days_held"

"""
Virtual “group portfolio” builder.

• list_groups()                → synthetic list generated from owners
• build_group_portfolio(slug)  → merge owners → one portfolio dict
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("group_portfolio")

# ──────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────
BASE_DIR         = Path(__file__).resolve().parents[2] / "data"
PRICES_FILE      = BASE_DIR / "prices" / "latest_prices.json"
PAST_CACHE_FILE  = BASE_DIR / "prices" / "past_prices.json"

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
def _load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as exc:
        logger.warning("Failed to load %s: %s", path, exc)
    return default

def _price_from_snapshot(snap: Any) -> Optional[float]:
    """
    Accept both the canonical dict shape and the legacy float-only
    snapshot rows.
    """
    if snap is None:
        return None
    if isinstance(snap, (int, float)):
        return float(snap)
    return snap.get("last_price")

# ──────────────────────────────────────────────────────────────
# Groups list (generated on the fly)
# ──────────────────────────────────────────────────────────────
def list_groups() -> List[Dict[str, Any]]:
    """
    Build a default set of groups based on the owners that exist.
    • “all”     – every owner
    • “adults”  – lucy + steve
    • “children”– alex + joe
    """

    from backend.common.portfolio_loader import list_portfolios
    owners = sorted({pf["owner"] for pf in list_portfolios()})

    return [
        {
            "slug":    "all",
            "name":    "All owners combined",
            "members": owners,
        },
        {
            "slug":    "adults",
            "name":    "Adults",
            "members": [o for o in owners if o.lower() in {"lucy", "steve"}],
        },
        {
            "slug":    "children",
            "name":    "Children",
            "members": [o for o in owners if o.lower() in {"alex", "joe"}],
        },
    ]


# ──────────────────────────────────────────────────────────────
# Core builder
# ──────────────────────────────────────────────────────────────
def build_group_portfolio(slug: str) -> Dict[str, Any]:
    groups = {g["slug"]: g for g in list_groups()}
    grp = groups.get(slug)
    if not grp:
        raise ValueError(f"Unknown group slug: {slug!r}")

    wanted = {o.lower() for o in grp["members"]}

    # Get portfolios to merge
    from backend.common.portfolio_loader import list_portfolios    # local import avoids cycles
    portfolios_to_merge = [
        pf for pf in list_portfolios()
        if pf.get("owner", "").lower() in wanted
    ]

    # Load price caches once
    latest_prices: Dict[str, Any] = _load_json(PRICES_FILE, {})
    past_cache:    Dict[str, Any] = _load_json(PAST_CACHE_FILE, {})

    merged_accounts: List[Dict[str, Any]] = []

    for pf in portfolios_to_merge:
        for acct in pf.get("accounts", []):
            owner = pf["owner"]
            acct_copy = acct.copy()
            acct_copy["owner"] = owner

            # decorate each holding with a snapshot price if missing
            for h in acct_copy.get("holdings", []):
                ticker_with_exchange = (h.get("ticker") or "").upper()
                ticker, exchange = (ticker_with_exchange.split(".", 1) + ["L"])[:2]

                if h.get(MARKET_VALUE_GBP) in (None, 0):
                    latest_price = _price_from_snapshot(latest_prices.get(ticker_with_exchange)) or 0.0
                    if latest_price:
                        h[MARKET_VALUE_GBP] = round(latest_price * (h.get("units") or 0), 2)

                if h.get(ACQUIRED_DATE) is None:
                    h[ACQUIRED_DATE] = datetime.today() - timedelta(days=365)
                acquired_df = load_meta_timeseries_range(ticker=ticker, exchange=exchange,
                                           start_date=h[ACQUIRED_DATE], end_date=h[ACQUIRED_DATE])
                if not h.get(DAYS_HELD):
                    # TODO calculate
                    h[DAYS_HELD] = 365

                # compute gain if not present
                if h.get(GAIN_GBP) is None:
                    cost = h.get(COST_BASIS_GBP) or h.get(EFFECTIVE_COST_BASIS_GBP) or 0.0
                    mv   = h.get(MARKET_VALUE_GBP) or 0.0
                    h[GAIN_GBP] = round(mv - cost, 2)

            merged_accounts.append(acct_copy)

    return {
        "slug":     slug,
        "name":     grp["name"],
        "accounts": merged_accounts,
    }
