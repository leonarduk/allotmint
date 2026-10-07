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
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.common.approvals import load_approvals
from backend.common.authz import identity_can_access_owner
from backend.common.data_loader import (
    DATA_BUCKET_ENV,
    PLOTS_PREFIX,
    list_plots,
    load_account_record,
    resolve_paths,
)
from backend.common.holding_utils import enrich_holding
from backend.common.holdings_rebuild import transaction_cost_hints
from backend.common.path_utils import safe_join
from backend.common.portfolio_loader import ACCOUNT_STEM_KEY
from backend.common.position_returns import attach_total_returns
from backend.common.ticker_utils import canonical_ticker
from backend.common.user_config import load_user_config
from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.timeseries.cache import cache_only
from backend.utils.pricing_dates import PricingDateCalculator

logger = logging.getLogger(__name__)


# Held tickers already reported as having no matching transaction pool, so the
# warning fires once per process rather than on every page request (same idea
# as ``_warned_missing_data_bucket`` in backend/routes/transactions.py).
_UNMATCHED_COST_WARNED: set[tuple[str, str, str]] = set()


def _read_account_transactions(
    owner: str, account: str, accounts_root: Optional[Path]
) -> Optional[List[Dict[str, Any]]]:
    """Return the account's transactions, or ``None`` when there is no usable file."""
    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = Path(accounts_root) if accounts_root else paths.accounts_root
    try:
        owner_dir = safe_join(root, owner)
        tx_path = next(
            (
                c
                for c in sorted(owner_dir.glob("*_transactions.json"))
                if c.stem[: -len("_transactions")].lower() == account.lower()
            ),
            None,
        )
        if tx_path is None:
            return None
        tx_data = json.loads(tx_path.read_text(encoding="utf-8"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read transactions to cost unknown-cost holdings: %s", sanitise_log_value(exc))
        return None
    if not isinstance(tx_data, dict):
        return []
    return [t for t in (tx_data.get("transactions") or []) if isinstance(t, dict)]


def _strip_suffix(ticker: str) -> str:
    """``VWRL.L`` -> ``VWRL``; a ticker with no exchange suffix is returned unchanged."""
    return ticker.rsplit(".", 1)[0] if "." in ticker else ticker


def _match_hint_key(ticker: str, hint_keys: List[str], held_bases: Dict[str, int]) -> Optional[str]:
    """Return the transaction pool key for held ``ticker``, or ``None``.

    An exact match always wins.  Otherwise a pool whose ticker differs only by
    an exchange suffix on one side (``VWRL`` vs ``VWRL.L``) is used, but only
    when exactly one pool fits and no other holding counted in ``held_bases``
    shares the same base symbol, so an ambiguous listing is never guessed at.
    """
    if ticker in hint_keys:
        return ticker
    # Pools are keyed canonically, so a held padded LSE EPIC ("BP.") matches
    # its "BP.L" pool exactly rather than via the base-symbol guess (#8600).
    canonical = canonical_ticker(ticker)
    if canonical in hint_keys:
        return canonical
    base = _strip_suffix(ticker)
    if held_bases.get(base, 0) != 1:
        return None
    candidates = [k for k in hint_keys if k == base or _strip_suffix(k) == ticker]
    return candidates[0] if len(candidates) == 1 else None


def _warn_unmatched(owner: str, account: str, ticker: str) -> None:
    key = (owner.lower(), account.lower(), ticker)
    if key in _UNMATCHED_COST_WARNED:
        return
    _UNMATCHED_COST_WARNED.add(key)
    logger.warning(
        "No transaction history matches zero-cost holding %s in %s/%s; its cost stays unknown",
        sanitise_log_value(ticker),
        sanitise_log_value(owner),
        sanitise_log_value(account),
    )


def _held_base_counts(holdings: List[Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for h in holdings:
        if isinstance(h, dict):
            base = _strip_suffix(str(h.get("ticker") or "").strip().upper())
            counts[base] = counts.get(base, 0) + 1
    return counts


def fill_missing_costs(owner: str, account: str, holdings: List[Any], accounts_root: Optional[Path] = None) -> None:
    """Cost zero-cost holdings from their transactions (in memory only).

    Mutates the dicts in ``holdings``; callers holding shared data should pass
    copies.  The transactions file is read and replayed once per call.

    A holding with no booked cost is otherwise valued at today's price (or the
    close on its ``acquired_date``), so its gain is a guess or a false £0.00.
    When the transactions give a fully known Section 104 pool cost it is used,
    even if the holding has an ``acquired_date``.  Otherwise an undated holding
    is dated from when its unknown-cost units arrived (the opening transfer-in)
    so ``enrich_holding`` derives the cost from the price on that date.  A
    non-zero booked cost always wins.  Never writes to the data files.
    """
    needy = [h for h in holdings if isinstance(h, dict) and not h.get("cost_basis_gbp")]
    if not needy:
        return
    transactions = _read_account_transactions(owner, account, accounts_root)
    if transactions is None:
        return
    hints = transaction_cost_hints(transactions)
    hint_keys = [k for k in hints if not k.startswith(("name:", "ref:"))]
    # A holding with a booked cost never takes a fill, so it must not make a
    # zero-cost sibling's base symbol look ambiguous (#8480).  Its own pool is
    # still off-limits to a suffix-only guess from that sibling.
    held_bases = _held_base_counts(needy)
    booked_keys = {
        canonical_ticker(str(h.get("ticker") or ""))
        for h in holdings
        if isinstance(h, dict) and h.get("cost_basis_gbp")
    }
    for h in needy:
        ticker = str(h.get("ticker") or "").strip().upper()
        if not ticker or _strip_suffix(ticker) == "CASH":  # cash has no transaction pool
            continue
        key = _match_hint_key(ticker, hint_keys, held_bases)
        if key in booked_keys and key not in (ticker, canonical_ticker(ticker)):
            key = None
        if key is None:
            _warn_unmatched(owner, account, ticker)
            continue
        cost, since = hints[key]
        if cost:
            h["cost_basis_gbp"] = cost
        elif since and not h.get("acquired_date"):
            h["acquired_date"] = since


def add_total_returns(owner: str, account: str, holdings: List[Any], accounts_root: Optional[Path] = None) -> None:
    """Add income and total-return fields to enriched ``holdings`` in place (#9038).

    Held tickers are matched to transaction pools with the same rules as
    :func:`fill_missing_costs`, so income lands on the holding whose cost it
    already explains.  Never writes to the data files.
    """
    transactions = _read_account_transactions(owner, account, accounts_root)
    held_bases = _held_base_counts(holdings)
    attach_total_returns(
        holdings,
        transactions,
        lambda ticker, keys: _match_hint_key(ticker, keys, held_bases),
    )


# ───────────────────────── trades helpers ─────────────────────────
def _local_trades_path(owner: str, accounts_root: Optional[Path] = None) -> Path:
    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = Path(accounts_root) if accounts_root else paths.accounts_root
    try:
        owner_dir = safe_join(root, owner)
    except ValueError as exc:
        raise FileNotFoundError("invalid owner") from exc
    return owner_dir / "trades.csv"


def _load_trades_local(owner: str, accounts_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = _local_trades_path(owner, accounts_root)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_trades_aws(owner: str) -> List[Dict[str, Any]]:
    bucket = os.getenv(DATA_BUCKET_ENV)
    if not bucket:
        return []

    key = f"{PLOTS_PREFIX}{owner}/trades.csv"
    try:
        import boto3  # type: ignore
        from botocore.exceptions import BotoCoreError, ClientError

        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj.get("Body")
        if not body:
            return []
        data = body.read().decode(encoding="utf-8", errors="replace").splitlines()
        return list(csv.DictReader(data))
    except (ClientError, BotoCoreError) as exc:
        logger.warning(
            "Failed to fetch trades %s from bucket %s: %s",
            sanitise_log_value(key),
            sanitise_log_value(bucket),
            sanitise_log_value(exc),
        )
    except ImportError as exc:
        logger.warning("boto3 not available for S3 trades fetch: %s", sanitise_log_value(exc))
    return []


def load_trades(owner: str, accounts_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Public helper. Keeps us self-contained so there's no circular dependency."""
    return _load_trades_local(owner, accounts_root) if config.app_env == "local" else _load_trades_aws(owner)


# ───────────────────────── generic helpers ───────────────────────
def _parse_date(s: str | None) -> Optional[dt.date]:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s).date()
    except ValueError:
        return None


# ─────────────────────── owners utility ──────────────────────────
def list_owners(
    accounts_root: Optional[Path] = None,
    current_user: Optional[str] = None,
) -> list[str]:
    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = Path(accounts_root) if accounts_root else paths.accounts_root
    owners: list[str] = []
    for pf in root.glob("*/person.json"):
        try:
            data = json.loads(pf.read_text())
            slug = data.get("owner") or data.get("slug")
            if slug and (not current_user or identity_can_access_owner(current_user, slug, data)):
                owners.append(slug)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Skipping owner file %s: %s", sanitise_log_value(pf), sanitise_log_value(exc))
            continue
    return owners


# ─────────────────────── owner-level builder ─────────────────────
def build_owner_portfolio(
    owner: str,
    accounts_root: Optional[Path] = None,
    *,
    root: Optional[Path] = None,
    pricing_date: Optional[dt.date] = None,
    include_account_stem: bool = False,
) -> Dict[str, Any]:
    """Build ``owner``'s portfolio from their account files.

    ``include_account_stem`` tags each account with its file stem under
    :data:`~backend.common.portfolio_loader.ACCOUNT_STEM_KEY` -- a stable,
    per-owner-unique key (``isa`` for ``<owner>/isa.json``) for callers that
    need to refer to an account across requests (#9496). It is off by default
    because ``AccountContract`` forbids extra keys, so API responses that
    serialise accounts directly must not carry it.
    """
    if root is not None:
        accounts_root = root
    calc = PricingDateCalculator(reporting_date=pricing_date)
    today = calc.today
    pricing_date = calc.reporting_date

    all_plots = list_plots(accounts_root)
    plots = [p for p in all_plots if p.owner == owner]
    if not plots:
        # Diagnostics for #5286: performance/tracking-error and its sibling
        # endpoints report this as a generic 404 "Owner not found", which is
        # indistinguishable from a genuinely-nonexistent owner. Logging the
        # total plot count discovered lets a real occurrence be told apart
        # from a transient empty/partial listing (e.g. an S3 listing hiccup
        # in list_plots) without requiring another blind investigation.
        logger.warning(
            "build_owner_portfolio: no plot found for owner=%s (total plots discovered=%s)",
            sanitise_log_value(owner),
            sanitise_log_value(len(all_plots)),
        )
        raise FileNotFoundError(f"No plot for owner '{owner}'")
    accounts_meta = plots[0].accounts

    trades = load_trades(owner, accounts_root)
    trades_this = 0
    for t in trades:
        d = _parse_date(t.get("date"))
        if d and d.year == today.year and d.month == today.month:
            trades_this += 1
    ucfg = load_user_config(owner, accounts_root)
    trades_rem = max(0, (ucfg.max_trades_per_month or 0) - trades_this)

    price_cache: dict[str, float] = {}
    approvals = load_approvals(owner, accounts_root)

    accounts: List[Dict[str, Any]] = []
    for meta in accounts_meta:
        raw = load_account_record(owner, meta, accounts_root)
        holdings_raw = raw.holdings
        fill_missing_costs(owner, str(meta), holdings_raw, accounts_root)

        # Page request: price from the timeseries cache only; the background
        # snapshot refresh does the live fetching (#7898).
        with cache_only():
            enriched = [
                enrich_holding(
                    h,
                    today,
                    price_cache,
                    approvals,
                    ucfg,
                    calc=calc,
                )
                for h in holdings_raw
            ]
        add_total_returns(owner, str(meta), enriched, accounts_root)
        val_gbp = sum(float(h.get("market_value_gbp") or 0.0) for h in enriched)

        account: Dict[str, Any] = {
            "account_type": raw.account_type or str(meta).upper(),
            "currency": raw.currency or "GBP",
            "last_updated": raw.last_updated,
            "value_estimate_gbp": val_gbp,
            "holdings": enriched,
        }
        if include_account_stem:
            account[ACCOUNT_STEM_KEY] = str(meta)
        accounts.append(account)

    total_val = sum(a["value_estimate_gbp"] for a in accounts)

    return {
        "owner": owner,
        "as_of": pricing_date.isoformat(),
        "trades_this_month": trades_this,
        "trades_remaining": trades_rem,
        "accounts": accounts,
        "total_value_estimate_gbp": total_val,
    }
