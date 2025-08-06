from __future__ import annotations

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
                if h.get("market_value_gbp") in (None, 0):
                    ticker = (h.get("ticker") or "").upper()
                    full_ticker = ticker
                    latest_price = _price_from_snapshot(latest_prices.get(full_ticker)) or 0.0
                    if latest_price:
                        h["market_value_gbp"] = round(latest_price * (h.get("units") or 0), 2)

                # compute gain if not present
                if h.get("gain_gbp") is None:
                    cost = h.get("cost_basis_gbp") or h.get("effective_cost_basis_gbp") or 0.0
                    mv   = h.get("market_value_gbp") or 0.0
                    h["gain_gbp"] = round(mv - cost, 2)

            merged_accounts.append(acct_copy)

    return {
        "slug":     slug,
        "name":     grp["name"],
        "accounts": merged_accounts,
    }
