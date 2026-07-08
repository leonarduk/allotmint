# backend/common/portfolio_loader.py
from __future__ import annotations

"""
Build rich "portfolio" dictionaries that the rest of the backend expects.

- list_portfolios()           -> [{ owner, person, accounts:[...] }, ...]
- load_portfolio(owner)       -> { ... }   (single owner helper, not used elsewhere)
"""

import json
import logging
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, cast

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

from backend.common.account_models import OwnerSummaryRecord
from backend.common.data_loader import (
    list_plots,  # owner -> ["isa", "sipp", ...]
    load_account,  # (owner, account) -> parsed JSON
    load_person_meta,  # (owner) -> {dob, ...}
    resolve_paths,
)
from backend.common.path_utils import safe_join
from backend.config import config
from backend.logging_setup import sanitise_log_value

log = logging.getLogger("portfolio_loader")


# ────────────────────────────────────────────────────────────────
# Private helpers
# ────────────────────────────────────────────────────────────────
def _load_accounts_for_owner(owner: str, acct_names: list[str]) -> list[dict]:
    """Load every <owner>/<account>.json and return the parsed dicts."""
    accounts: list[dict] = []
    for name in acct_names:
        try:
            acct = load_account(owner, name)
            accounts.append(acct)
        except FileNotFoundError:
            log.warning("Account file missing: %s/%s.json", sanitise_log_value(owner), sanitise_log_value(name))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            log.warning(
                "Failed to parse %s/%s.json -> %s",
                sanitise_log_value(owner),
                sanitise_log_value(name),
                sanitise_log_value(exc),
            )
    return accounts


def _build_owner_portfolio(owner_summary: OwnerSummaryRecord) -> dict:
    """
    owner_summary ≅ OwnerSummaryRecord(owner='alex', accounts=['isa', 'sipp'])
    returns        ≅ {
                        'owner'   : 'alex',
                        'person'  : {...},          # person.json (may be {})
                        'accounts': [ {...}, ... ]  # parsed account JSON
                      }
    """
    owner = owner_summary.owner
    names = owner_summary.accounts

    return {
        "owner": owner,
        "person": load_person_meta(owner),
        "accounts": _load_accounts_for_owner(owner, names),
    }


# ────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────
def list_portfolios() -> list[dict]:
    """Discover every owner / account on disk and build a portfolio tree."""
    portfolios: list[dict] = []
    for owner_row in list_plots():
        portfolios.append(_build_owner_portfolio(owner_row))
    return portfolios


# (Optional) convenience helper - not used by the current backend, but handy.
def load_portfolio(owner: str) -> dict | None:
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
    accounts_root: Path | None = None,
) -> dict[str, object]:
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
    try:
        owner_dir = safe_join(root, owner)
    except ValueError as exc:
        raise FileNotFoundError("invalid owner") from exc

    account_lc = account.lower()
    tx_path = None
    for candidate in owner_dir.glob("*_transactions.json"):
        stem = candidate.stem.replace("_transactions", "")
        if stem.lower() == account_lc:
            tx_path = candidate
            break

    if not tx_path:
        log.error(
            "Transaction file missing: %s",
            sanitise_log_value(owner_dir / f"{account}_transactions.json"),
        )
        return {}

    try:
        tx_data = json.loads(tx_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.error("Failed to read %s: %s", sanitise_log_value(tx_path), sanitise_log_value(exc))
        return {}

    if not isinstance(tx_data, dict):
        log.error("Malformed transaction file %s: expected object, got %s", sanitise_log_value(tx_path), type(tx_data).__name__)
        return {}

    out = compute_holdings_from_transactions(tx_data, owner, account)

    try:
        acct_path = safe_join(owner_dir, f"{account.lower()}.json")
    except ValueError:
        log.error("Invalid account name: path traversal blocked")
        return out
    try:
        acct_path.write_text(json.dumps(out, indent=2))
    except OSError as exc:
        log.error("Failed to write holdings to %s: %s", acct_path, exc)
    return out


def compute_holdings_from_transactions(
    tx_data: dict[str, Any],
    owner: str,
    account: str,
) -> dict[str, object]:
    """Compute holdings from a parsed transactions document.

    This is the core computation shared by the path-based local store and the
    S3-backed store.  It mirrors the logic originally in
    :func:`rebuild_account_holdings` but accepts a pre-loaded transaction dict
    instead of reading from disk, so callers control where the raw data comes
    from and where the result is persisted.

    Parameters
    ----------
    tx_data:
        Parsed transaction document (must have a ``"transactions"`` key whose
        value is a list of transaction dicts).
    owner:
        Portfolio owner slug.
    account:
        Account name, e.g. ``"isa"`` or ``"sipp"``.

    Returns
    -------
    dict
        Holdings structure with keys ``owner``, ``account_type``, ``currency``,
        ``last_updated``, and ``holdings``.
    """
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

    for t in cast("list[dict[str, Any]]", tx_data.get("transactions", [])):
        ttype = (t.get("type") or "").upper()
        ticker = (t.get("ticker") or "").upper()

        if ttype in TYPE_SIGN and ticker:
            raw = next(
                (t[k] for k in ("shares", "quantity", "units") if k in t and t[k] is not None),
                None,
            )
            try:
                qty = float(raw) if isinstance(raw, (int, float, str)) else 0.0
            except (TypeError, ValueError):
                log.warning("Skipping unparseable quantity for ticker=%s raw=%r", sanitise_log_value(ticker), raw)
                continue
            if abs(qty) > 1_000_000:  # detect PP's 1e8 scaling
                qty /= SHARE_SCALE
            qty *= TYPE_SIGN[ttype]
            ledger[ticker] += qty

            if ttype in {"BUY", "PURCHASE", "TRANSFER_IN"}:
                d_raw = str(t.get("date") or "")[:10]
                if _ISO_DATE_RE.match(d_raw):
                    if not acquisition.get(ticker) or d_raw > acquisition[ticker]:
                        acquisition[ticker] = d_raw
                elif d_raw:
                    log.warning("Skipping non-ISO date for ticker=%s date=%r", sanitise_log_value(ticker), d_raw)

        elif ttype in CASH_SIGNS:
            amount_minor = t.get("amount_minor")
            try:
                amt = float(amount_minor) if isinstance(amount_minor, (int, float, str)) else 0.0
            except (TypeError, ValueError):
                log.warning("Skipping unparseable amount_minor for ttype=%s raw=%r", ttype, amount_minor)
                continue
            ledger["CASH.GBP"] += (amt / 100.0) * CASH_SIGNS[ttype]

    holdings: list[dict[str, object]] = []
    for tick, qty in ledger.items():
        if abs(qty) < 1e-9:
            continue
        h: dict[str, object] = {"ticker": tick, "units": qty, "cost_basis_gbp": 0.0}
        acq_date = acquisition.get(tick)
        if acq_date:
            h["acquired_date"] = acq_date
        holdings.append(h)

    return {
        "owner": owner,
        "account_type": account.upper(),
        "currency": str(tx_data.get("currency", "GBP")),
        "last_updated": date.today().isoformat(),
        "holdings": holdings,
    }
