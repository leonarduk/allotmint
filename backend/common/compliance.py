from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.common.account_scaffold import (
    _parse_date,
    ensure_owner_scaffold,
    load_transactions,
)
from backend.common.approvals import is_approval_valid, load_approvals
from backend.common.instruments import get_instrument_meta
from backend.common.user_config import UserConfig, load_user_config
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

# Re-exported for backward compatibility: callers importing
# ``ensure_owner_scaffold``/``load_transactions`` from this module continue to
# work unchanged even though the implementations now live in
# backend.common.account_scaffold (issue: open-core split prep).
__all__ = [
    "ensure_owner_scaffold",
    "load_transactions",
    "check_owner",
    "check_trade",
    "evaluate_trades",
]


def _check_transactions(owner: str, txs: List[Dict[str, Any]], accounts_root: Optional[Path] = None) -> Dict[str, Any]:
    """Run compliance checks on a list of transactions."""

    warnings: List[str] = []
    try:
        approvals = load_approvals(owner, accounts_root)
    except FileNotFoundError:
        approvals = {}

    try:
        ucfg = load_user_config(owner, accounts_root)
    except FileNotFoundError:
        ucfg = UserConfig(
            hold_days_min=config.hold_days_min,
            max_trades_per_month=config.max_trades_per_month,
            approval_exempt_types=config.approval_exempt_types,
            approval_exempt_tickers=config.approval_exempt_tickers,
        )
    exempt_tickers = {t.upper() for t in (ucfg.approval_exempt_tickers or [])}
    exempt_types = {t.upper() for t in (ucfg.approval_exempt_types or [])}

    today = date.today()

    # trade count rule
    counts: Dict[str, int] = defaultdict(int)
    for t in txs:
        d = _parse_date(t.get("date"))
        if not d:
            continue
        key = f"{d.year:04d}-{d.month:02d}"
        counts[key] += 1
    for month, cnt in counts.items():
        if cnt > (ucfg.max_trades_per_month or 0):
            warnings.append(f"{cnt} trades in {month} (max {ucfg.max_trades_per_month})")
            logger.info(
                "%s MAX_TRADES_PER_MONTH %s %s",
                datetime.now(UTC).isoformat(),
                sanitise_log_value(owner),
                sanitise_log_value(month),
            )

    # holding period rule
    last_buy: Dict[str, date] = {}
    positions: Dict[str, float] = defaultdict(float)
    for t in txs:
        d = _parse_date(t.get("date"))
        if not d:
            continue
        ticker = (t.get("ticker") or "").upper()
        action = (t.get("type") or t.get("kind") or "").lower()
        raw_shares = t.get("shares")
        try:
            shares = float(raw_shares or 0.0)
        except (TypeError, ValueError):
            logger.warning(
                "invalid share count %s in transaction (ticker=%s, date=%s)",
                sanitise_log_value(raw_shares),
                sanitise_log_value(t.get("ticker")),
                sanitise_log_value(t.get("date")),
            )
            shares = 0.0
        if action in {"buy", "purchase"}:
            last_buy[ticker] = d
            positions[ticker] += shares
        elif action == "sell":
            positions[ticker] -= shares
            acq = last_buy.get(ticker)
            if acq and (d - acq).days < (ucfg.hold_days_min or 0):
                days = (d - acq).days
                warnings.append(f"Sold {ticker} after {days} days (min {ucfg.hold_days_min})")
                logger.info(
                    "%s HOLD_DAYS_MIN %s %s",
                    datetime.now(UTC).isoformat(),
                    sanitise_log_value(owner),
                    sanitise_log_value(ticker),
                )

            meta = get_instrument_meta(ticker)
            instr_type = (meta.get("instrumentType") or meta.get("instrument_type") or "").upper()
            asset_class = (meta.get("assetClass") or meta.get("asset_class") or "").upper()
            sector = (meta.get("sector") or "").upper()
            is_commodity = asset_class == "COMMODITY" or sector == "COMMODITY"
            is_etf = instr_type == "ETF"
            exempt_type = instr_type in exempt_types
            if is_etf and is_commodity:
                exempt_type = False
            needs_approval = not (ticker in exempt_tickers or ticker.split(".")[0] in exempt_tickers or exempt_type)
            if needs_approval:
                appr = approvals.get(ticker) or approvals.get(ticker.split(".")[0])
                if not (appr and is_approval_valid(appr, d)):
                    warnings.append(f"Sold {ticker} without approval")
                    logger.info(
                        "%s APPROVAL_REQUIRED %s %s",
                        datetime.now(UTC).isoformat(),
                        sanitise_log_value(owner),
                        sanitise_log_value(ticker),
                    )
            if positions.get(ticker, 0) <= 0:
                positions.pop(ticker, None)
                last_buy.pop(ticker, None)

    # compute hold countdowns for open positions
    hold_countdowns: Dict[str, int] = {}
    hold_min = ucfg.hold_days_min or 0
    for ticker, acq in last_buy.items():
        days_held = (today - acq).days
        if days_held < hold_min and positions.get(ticker, 0) > 0:
            hold_countdowns[ticker] = hold_min - days_held

    # remaining trades this month
    current_month = f"{today.year:04d}-{today.month:02d}"
    trades_this_month = counts.get(current_month, 0)
    trades_remaining = max(0, (ucfg.max_trades_per_month or 0) - trades_this_month)

    return {
        "owner": owner,
        "warnings": warnings,
        "trade_counts": dict(counts),
        "hold_countdowns": hold_countdowns,
        "trades_this_month": trades_this_month,
        "trades_remaining": trades_remaining,
    }


def check_owner(
    owner: str,
    accounts_root: Optional[Path] = None,
    *,
    scaffold_missing: bool = False,
) -> Dict[str, Any]:
    """Return compliance warnings for an owner."""
    txs = load_transactions(owner, accounts_root, scaffold_missing=scaffold_missing)
    return _check_transactions(owner, txs, accounts_root)


def check_trade(
    trade: Dict[str, Any],
    accounts_root: Optional[Path] = None,
    *,
    scaffold_missing: bool = False,
) -> Dict[str, Any]:
    """Validate a proposed trade for compliance issues.

    The trade is evaluated in the context of the owner's existing transactions.
    """

    owner = trade.get("owner")
    if not owner:
        raise ValueError("owner is required")
    txs = load_transactions(owner, accounts_root, scaffold_missing=scaffold_missing)
    txs.append(trade)
    return _check_transactions(owner, txs, accounts_root)


def evaluate_trades(
    owner: str,
    txs: List[Dict[str, Any]],
    accounts_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Attach compliance warnings to each trade in ``txs``.

    Transactions should be ordered chronologically.  The function evaluates
    the growing history of trades and records only the warnings triggered by
    the current transaction.
    """

    evaluated: List[Dict[str, Any]] = []
    history: List[Dict[str, Any]] = []
    seen: List[str] = []
    for tx in txs:
        check = _check_transactions(owner, history + [tx], accounts_root)
        new_warnings = [w for w in check["warnings"] if w not in seen]
        evaluated.append({**tx, "warnings": new_warnings})
        history.append(tx)
        seen.extend(new_warnings)
    return evaluated
