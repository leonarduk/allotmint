"""
Group-level portfolio utilities for AllotMint
============================================

• list_groups()            – return group definitions
• build_group_portfolio()  – aggregate owner portfolios for one group

Auto-generation:
----------------
If *data/groups.json* is missing we build three default groups from the
person.json files found under data-sample/accounts/<owner>/person.json:

    children : owners whose age  < 18
    adults   : owners whose age >= 18
    all      : every owner

This removes the need for a separate groups.json during early setup.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, DefaultDict

# ───────────────────────────────────────────────────────────────
# File locations (adjust if your repo uses different paths)
# ───────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = _REPO_ROOT / "data"
print("REPO_ROOT", _REPO_ROOT)
GROUPS_FILE = Path(DATA_ROOT, "groups.json")                      # custom groups
PLOTS_ROOT = DATA_ROOT / "accounts"           # per-owner accounts

TODAY = dt.date.today()

# ───────────────────────────────────────────────────────────────
# Helpers for deriving age from person.json
# ───────────────────────────────────────────────────────────────
def _derive_age(info: dict) -> int | None:
    """Return integer age or None if dob/age missing or malformed."""
    if "age" in info:
        try:
            return int(info["age"])
        except Exception:
            return None
    dob = info.get("dob") or info.get("birth_date")
    if not dob:
        return None
    try:
        dob_dt = dt.datetime.fromisoformat(dob).date()
        return (TODAY - dob_dt).days // 365
    except Exception:
        return None


def _auto_groups_from_person_json() -> List[Dict[str, Any]]:
    """Scan accounts/*/person.json and build children/adults/all groups."""
    adults: list[str] = []
    children: list[str] = []
    everyone: list[str] = []

    person_files = list(PLOTS_ROOT.glob("*/person.json"))
    print(f"[groups] found {len(person_files)} person.json files under {PLOTS_ROOT}")

    for person_file in person_files:
        try:
            info = json.loads(person_file.read_text())
        except Exception:
            continue

        slug = info.get("owner") or info.get("slug")
        if not slug:
            continue

        age = _derive_age(info)
        if age is None:
            continue

        everyone.append(slug)
        (children if age < 18 else adults).append(slug)

    return [
        {"slug": "children", "name": "Children", "members": children},
        {"slug": "adults",   "name": "Adults",   "members": adults},
        {"slug": "all",      "name": "All",      "members": everyone},
    ]


# ───────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────
def list_groups() -> List[Dict[str, Any]]:
    """
    Return a list of group dicts.

    1. If *data/groups.json* exists, load and return it verbatim.
    2. Otherwise, auto-generate children/adults/all from accounts/*/person.json.
    """
    if GROUPS_FILE.exists():
        with GROUPS_FILE.open() as f:
            return json.load(f)

    if not PLOTS_ROOT.exists():
        raise FileNotFoundError(
            "data/groups.json not found and no plot directories present; "
            "cannot build default groups"
        )

    return _auto_groups_from_person_json()


def build_group_portfolio(slug: str, env: Optional[str] = None) -> Dict[str, Any]:
    """
    Aggregate the owner portfolios for the requested group.

    Lazy-imports build_owner_portfolio to avoid circular dependency.
    """
    # ── LAZY import ────────────────────────────────────────────
    from backend.common.portfolio import build_owner_portfolio

    env = (env or os.getenv("ALLOTMINT_ENV", "local")).lower()
    today_iso = TODAY.isoformat()

    grp = _find_group(slug)
    members: List[str] = grp.get("members", [])

    owner_portfolios = [build_owner_portfolio(m, env=env) for m in members]

    # ---- aggregate accounts ----------------------------------
    acct_map: DefaultDict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "account_type": "",
            "currency": "GBP",
            "last_updated": today_iso,
            "value_estimate_gbp": 0.0,
            "holdings": [],
        }
    )

    trades_this_month = 0
    trades_remaining = 0

    for op in owner_portfolios:
        trades_this_month += op.get("trades_this_month", 0)
        trades_remaining += op.get("trades_remaining", 0)

        for acct in op.get("accounts", []):
            a_type = acct.get("account_type", "").upper()
            g_acct = acct_map[a_type]
            g_acct["account_type"] = a_type
            g_acct["currency"] = acct.get("currency", "GBP")
            g_acct["value_estimate_gbp"] += acct.get("value_estimate_gbp", 0.0)
            g_acct["holdings"].extend(acct.get("holdings", []))

    accounts = list(acct_map.values())
    total_value = sum(a["value_estimate_gbp"] for a in accounts)

    return {
        "group": slug.lower(),
        "name": grp.get("name", slug.title()),
        "members": members,
        "as_of": today_iso,
        "trades_this_month": trades_this_month,
        "trades_remaining": trades_remaining,
        "accounts": accounts,
        "total_value_estimate_gbp": total_value,
    }


# ───────────────────────────────────────────────────────────────
# Internal helper
# ───────────────────────────────────────────────────────────────
def _find_group(slug: str) -> Dict[str, Any]:
    slug = slug.lower()
    for g in list_groups():
        if (g.get("slug") or "").lower() == slug:
            return g
    raise KeyError(f"Unknown group slug '{slug}'")
