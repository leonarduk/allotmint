# backend/common/portfolio.py
from __future__ import annotations

"""
Owner-level portfolio builder for AllotMint
==========================================

- build_owner_portfolio(owner)
- list_owners()
"""

import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend import config as config_module
from backend.common.constants import (
    ACQUIRED_DATE,
    COST_BASIS_GBP,
    UNITS,
    TICKER,
)
from backend.common.data_loader import list_plots, load_account
from backend.common.holding_utils import enrich_holding

config = config_module.config


# ───────────────────────── trades helpers ─────────────────────────
def _local_trades_path(owner: str) -> Path:
    return Path(config.accounts_root) / owner / "trades.csv"


def _load_trades_local(owner: str) -> List[Dict[str, Any]]:
    path = _local_trades_path(owner)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_trades_aws(owner: str) -> List[Dict[str, Any]]:
    # TODO: implement S3 lookup once infra is in place
    return []


def load_trades(owner: str) -> List[Dict[str, Any]]:
    """Public helper. Keeps us self-contained so there's no circular dependency."""
    return (
        _load_trades_local(owner)
        if config_module.get_config().get("app_env") == "local"
        else _load_trades_aws(owner)
    )


# ───────────────────────── generic helpers ───────────────────────
def _parse_date(s: str | None) -> Optional[dt.date]:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s).date()
    except Exception:
        return None


# ─────────────────────── owners utility ──────────────────────────
def list_owners() -> list[str]:
    owners: list[str] = []
    for pf in Path(config.accounts_root).glob("*/person.json"):
        try:
            data = json.loads(pf.read_text())
            slug = data.get("owner") or data.get("slug")
            if slug:
                owners.append(slug)
        except Exception:
            continue
    return owners


# ─────────────────────── owner-level builder ─────────────────────
def build_owner_portfolio(owner: str) -> Dict[str, Any]:
    today = dt.date.today()

    plots = [p for p in list_plots() if p.get("owner") == owner]
    if not plots:
        raise FileNotFoundError(f"No plot for owner '{owner}'")
    accounts_meta = plots[0].get("accounts", [])

    trades = load_trades(owner)
    trades_this = 0
    for t in trades:
        d = _parse_date(t.get("date"))
        if d and d.year == today.year and d.month == today.month:
            trades_this += 1
    trades_rem = max(0, config.max_trades_per_month - trades_this)

    price_cache: dict[str, float] = {}

    accounts: List[Dict[str, Any]] = []
    for meta in accounts_meta:
        raw = load_account(owner, meta)
        holdings_raw = raw.get("holdings", [])

        enriched = [
            enrich_holding(h, today, price_cache) for h in holdings_raw
        ]
        val_gbp = sum(float(h.get("market_value_gbp") or 0.0) for h in enriched)

        accounts.append(
            {
                "account_type": raw.get("account_type", str(meta).upper()),
                "currency": raw.get("currency", "GBP"),
                "last_updated": raw.get("last_updated"),
                "value_estimate_gbp": val_gbp,
                "holdings": enriched,
            }
        )

    return {
        "owner": owner,
        "as_of": today.isoformat(),
        "trades_this_month": trades_this,
        "trades_remaining": trades_rem,
        "accounts": accounts,
        "total_value_estimate_gbp": sum(a["value_estimate_gbp"] for a in accounts),
    }
