"""
Common portfolio helpers

• list_all_unique_tickers()     → returns all tickers in every portfolio
• get_security_meta(tkr)        → basic metadata from portfolios
• aggregate_by_ticker(tree)     → one row per ticker with latest-price snapshot
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

from backend.common.portfolio_loader import list_portfolios  # existing helper

logger = logging.getLogger("portfolio_utils")

# ──────────────────────────────────────────────────────────────
# Numeric helper
# ──────────────────────────────────────────────────────────────
def _safe_num(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ──────────────────────────────────────────────────────────────
# Snapshot loader (last_price / deltas)
# ──────────────────────────────────────────────────────────────
def _load_snapshot() -> Dict[str, Dict]:
    path = Path("data/prices/latest_prices.json")
    if not path.exists():
        logger.warning("Price snapshot not found: %s", path)
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        logger.error("Failed to parse snapshot %s: %s", path, exc)
        return {}


_PRICE_SNAPSHOT: Dict[str, Dict] = _load_snapshot()


def refresh_snapshot_in_memory(new_snapshot: Dict[str, Dict] | None = None):
    """Call this from /prices/refresh when you write a new JSON snapshot."""
    global _PRICE_SNAPSHOT
    _PRICE_SNAPSHOT = new_snapshot or _load_snapshot()
    logger.debug("In-memory price snapshot refreshed, %d tickers",
                 len(_PRICE_SNAPSHOT))

# ──────────────────────────────────────────────────────────────
# Securities universe helpers (needed by other modules)
# ──────────────────────────────────────────────────────────────
def _build_securities_from_portfolios() -> Dict[str, Dict]:
    securities: Dict[str, Dict] = {}
    for pf in list_portfolios():
        for acct in pf.get("accounts", []):
            for h in acct.get("holdings", []):
                tkr = (h.get("ticker") or "").upper()
                if not tkr:
                    continue
                securities[tkr] = {
                    "ticker": tkr,
                    "name":   h.get("name", tkr),
                }
    return securities


_SECURITIES = _build_securities_from_portfolios()


def get_security_meta(ticker: str) -> Dict | None:
    """Return {'ticker', 'name'} derived from current portfolios."""
    return _SECURITIES.get(ticker.upper())


def list_all_unique_tickers() -> List[str]:
    """Flat list of every distinct ticker in all portfolios (upper-case)."""
    return list(_SECURITIES.keys())

# ──────────────────────────────────────────────────────────────
# Core aggregation
# ──────────────────────────────────────────────────────────────
def aggregate_by_ticker(portfolio: dict) -> List[dict]:
    """
    Collapse a nested portfolio tree into one row per ticker,
    enriched with latest-price snapshot.
    """
    rows: Dict[str, dict] = {}

    for account in portfolio.get("accounts", []):
        for h in account.get("holdings", []):
            tkr = (h.get("ticker") or "").upper()
            if not tkr:
                continue

            row = rows.setdefault(
                tkr,
                {
                    "ticker":           tkr,
                    "name":             h.get("name", tkr),
                    "units":            0.0,
                    "market_value_gbp": 0.0,
                    "gain_gbp":         0.0,
                    "cost_gbp":         0.0,
                    "last_price_gbp":   None,
                    "last_price_date":  None,
                    "change_7d_pct":    None,
                    "change_30d_pct":   None,
                },
            )

            # accumulate units & cost
            row["units"] += _safe_num(h.get("units"))
            row["cost_gbp"] += _safe_num(h.get("cost_gbp"))

            # attach snapshot if present
            snap = _PRICE_SNAPSHOT.get(tkr)
            if snap:
                price = snap["last_price"]
                row["last_price_gbp"]  = price
                row["last_price_date"] = snap["last_price_date"]
                row["change_7d_pct"]   = snap["change_7d_pct"]
                row["change_30d_pct"]  = snap["change_30d_pct"]
                row["market_value_gbp"] = round(row["units"] * price, 2)
                row["gain_gbp"] = round(row["market_value_gbp"] - row["cost_gbp"], 2)

            # pass-through misc attributes (first non-null wins)
            for k in ("asset_class", "region", "owner"):
                if k not in row and h.get(k) is not None:
                    row[k] = h[k]

    return list(rows.values())
