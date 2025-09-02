# backend/common/portfolio_loader.py
from __future__ import annotations

"""
Build rich "portfolio" dictionaries that the rest of the backend expects.

- list_portfolios()           -> [{ owner, person, accounts:[...] }, ...]
- load_portfolio(owner)       -> { ... }   (single owner helper, not used elsewhere)
"""

import json
import logging
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from backend.common.data_loader import (
    list_plots,  # owner -> ["isa", "sipp", ...]
    load_account,  # (owner, account) -> parsed JSON
    load_person_meta,  # (owner) -> {dob, ...}
    resolve_paths,
)
from backend.config import config

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
        except (OSError, ValueError, json.JSONDecodeError) as exc:
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
    owner = owner_summary["owner"]
    names = owner_summary["accounts"]

    return {
        "owner": owner,
        "person": load_person_meta(owner),
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


# ---------------------------------------------------------------------------
# Holdings rebuild helpers
# ---------------------------------------------------------------------------
def rebuild_account_holdings(
    owner: str,
    account: str,
    accounts_root: Optional[Path] = None,
) -> Dict[str, any]:
    """Recreate ``<account>.json`` from its ``*_transactions.json`` file.

    The implementation mirrors the logic from
    :func:`backend.utils.positions.extract_holdings_from_transactions` but
    operates on the normalised JSON transaction files used by the API.  Each
    transaction is applied to a simple security ledger to arrive at the latest
    position sizes.  A cash balance is derived from deposit/withdrawal style
    records.

    Parameters
    ----------
    owner:
        Portfolio owner slug.
    account:
        Account name, e.g. ``"isa"`` or ``"sipp"`` (case-insensitive).
    accounts_root:
        Optional override for the accounts directory; defaults to the
        configured ``config.accounts_root``.

    Returns
    -------
    dict
        The holdings structure that was written to disk.
    """

    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = Path(accounts_root) if accounts_root else paths.accounts_root
    owner_dir = root / owner
    tx_path = owner_dir / f"{account.lower()}_transactions.json"
    if not tx_path.exists():
        log.error("Transaction file missing: %s", tx_path)
        return {}

    try:
        tx_data = json.loads(tx_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.error("Failed to read %s: %s", tx_path, exc)
        return {}

    TYPE_SIGN = {
        "BUY": 1,
        "PURCHASE": 1,
        "SELL": -1,
        "TRANSFER_IN": 1,
        "TRANSFER_OUT": -1,
        "REMOVAL": -1,
    }
    CASH_SIGNS = {
        "DEPOSIT": 1,
        "WITHDRAWAL": -1,
        "DIVIDENDS": 1,
        "INTEREST": 1,
    }
    SHARE_SCALE = 10**8

    ledger: defaultdict[str, float] = defaultdict(float)
    acquisition: dict[str, str] = {}

    for t in tx_data.get("transactions", []):
        ttype = (t.get("type") or "").upper()
        ticker = (t.get("ticker") or "").upper()

        if ttype in TYPE_SIGN and ticker:
            raw = t.get("shares") or t.get("quantity")
            try:
                qty = float(raw or 0.0)
            except (TypeError, ValueError):
                continue
            if abs(qty) > 1_000_000:  # detect PP's 1e8 scaling
                qty /= SHARE_SCALE
            qty *= TYPE_SIGN[ttype]
            ledger[ticker] += qty

            if ttype in {"BUY", "PURCHASE", "TRANSFER_IN"}:
                d = (t.get("date") or "")[:10]
                if d and (not acquisition.get(ticker) or d > acquisition[ticker]):
                    acquisition[ticker] = d

        elif ttype in CASH_SIGNS:
            try:
                amt = float(t.get("amount_minor") or 0.0) / 100.0
            except (TypeError, ValueError):
                continue
            ledger["CASH.GBP"] += amt * CASH_SIGNS[ttype]

    holdings = []
    for tick, qty in ledger.items():
        if abs(qty) < 1e-9:
            continue
        h: Dict[str, any] = {"ticker": tick, "units": qty, "cost_basis_gbp": 0.0}
        acq_date = acquisition.get(tick)
        if acq_date:
            h["acquired_date"] = acq_date
        holdings.append(h)

    out = {
        "owner": owner,
        "account_type": account.upper(),
        "currency": tx_data.get("currency", "GBP"),
        "last_updated": date.today().isoformat(),
        "holdings": holdings,
    }

    acct_path = owner_dir / f"{account.lower()}.json"
    try:
        acct_path.write_text(json.dumps(out, indent=2))
    except OSError as exc:
        log.error("Failed to write holdings to %s: %s", acct_path, exc)
    return out
