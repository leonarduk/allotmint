"""Build rich "portfolio" dictionaries that the rest of the backend expects.

- list_portfolios()           -> [{ owner, person, accounts:[...] }, ...]
- load_portfolio(owner)       -> { ... }   (single owner helper, not used elsewhere)
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List

from backend.common.data_loader import (
    list_plots,  # owner -> ["isa", "sipp", ...]
    load_account,  # (owner, account) -> parsed JSON
    load_person_meta,  # (owner) -> {dob, ...}
)

log = logging.getLogger("portfolio_loader")


# ────────────────────────────────────────────────────────────────
# Private helpers
# ────────────────────────────────────────────────────────────────
def _load_accounts_for_owner(owner: str, acct_names: List[str]) -> List[Dict]:
    """Load every <owner>/<account>.json and return the parsed dicts."""
    accounts: List[Dict] = []
    for name in acct_names:
        try:
            acct = load_account(owner, name)
            accounts.append(acct)
        except FileNotFoundError:
            log.warning("Account file missing: %s/%s.json", owner, name)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            log.warning("Failed to parse %s/%s.json -> %s", owner, name, exc)
    return accounts


def _build_owner_portfolio(owner_summary: Dict) -> Dict:
    """
    owner_summary ≅ {'owner': 'alex', 'accounts': ['isa', 'sipp']}
    returns        ≅ {
                        'owner'   : 'alex',
                        'person'  : {...},          # person.json (may be {})
                        'accounts': [ {...}, ... ]  # parsed account JSON
                      }
    """
    owner   = owner_summary["owner"]
    names   = owner_summary["accounts"]

    return {
        "owner"   : owner,
        "person"  : load_person_meta(owner),
        "accounts": _load_accounts_for_owner(owner, names),
    }


# ────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────
def list_portfolios() -> List[Dict]:
    """Discover every owner / account on disk and build a portfolio tree."""
    portfolios: List[Dict] = []
    for owner_row in list_plots():
        portfolios.append(_build_owner_portfolio(owner_row))
    return portfolios


# (Optional) convenience helper - not used by the current backend, but handy.
def load_portfolio(owner: str) -> Dict | None:
    """Return a single owner's portfolio tree, or None if owner not found."""
    for pf in list_portfolios():
        if pf["owner"].lower() == owner.lower():
            return pf
    return None
