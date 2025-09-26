from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.common.approvals import is_approval_valid, load_approvals
from backend.common.data_loader import resolve_paths
from backend.common.instruments import get_instrument_meta
from backend.common.user_config import load_user_config
from backend.config import config

logger = logging.getLogger("compliance")


def _default_settings_payload() -> Dict[str, Any]:
    """Build default settings for newly created owners."""

    payload: Dict[str, Any] = {}
    if config.hold_days_min is not None:
        payload["hold_days_min"] = config.hold_days_min
    else:
        payload["hold_days_min"] = 0

    if config.max_trades_per_month is not None:
        payload["max_trades_per_month"] = config.max_trades_per_month
    else:
        payload["max_trades_per_month"] = 0

    if config.approval_exempt_types:
        payload["approval_exempt_types"] = config.approval_exempt_types
    else:
        payload["approval_exempt_types"] = []

    if config.approval_exempt_tickers:
        payload["approval_exempt_tickers"] = config.approval_exempt_tickers
    else:
        payload["approval_exempt_tickers"] = []

    return payload


def _ensure_owner_scaffold(owner: str, owner_dir: Path) -> None:
    """Create the default directory and files for ``owner`` if absent."""

    owner_dir.mkdir(parents=True, exist_ok=True)

    defaults: Dict[str, Dict[str, Any]] = {
        "settings.json": _default_settings_payload(),
        "approvals.json": {"approvals": []},
        "person.json": {
            "owner": owner,
            "holdings": [],
            "viewers": [],
        },
        f"{owner}_transactions.json": {
            "account_type": "brokerage",
            "transactions": [],
        },
    }

    for filename, payload in defaults.items():
        path = owner_dir / filename
        if path.exists():
            continue
        try:
            path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        except OSError as exc:
            logger.warning("failed to create default %s for %s: %s", filename, owner, exc)


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val).date()
    except Exception:
        return None


def ensure_owner_scaffold(owner: str, accounts_root: Optional[Path] = None) -> Path:
    """Create the default compliance scaffold for ``owner`` if needed.

    Returns the resolved owner directory after ensuring the default files are
    present.
    """
    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = Path(accounts_root) if accounts_root else paths.accounts_root
    owner_dir = root / owner
    _ensure_owner_scaffold(owner, owner_dir)
    return owner_dir


def load_transactions(
    owner: str,
    accounts_root: Optional[Path] = None,
    *,
    scaffold_missing: bool = False,
) -> List[Dict[str, Any]]:
    """Load all transactions for ``owner`` sorted by date.

    By default the function now raises :class:`FileNotFoundError` when the owner
    directory is absent.  Administrative callers that want to bootstrap a new
    owner can opt-in to scaffolding by passing ``scaffold_missing=True``.

    """
    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = Path(accounts_root) if accounts_root else paths.accounts_root
    owner_dir = root / owner
    if not owner_dir.exists():
        raise FileNotFoundError(owner_dir)
    _ensure_owner_scaffold(owner, owner_dir)

    results: List[Dict[str, Any]] = []
    for path in owner_dir.glob("*_transactions.json"):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        acct = data.get("account_type", path.stem.replace("_transactions", ""))
        for t in data.get("transactions", []):
            results.append({"account": acct, **t})

    def sort_key(tx: Dict[str, Any]):
        d = _parse_date(tx.get("date"))
        return d or date.min

    results.sort(key=sort_key)
    return results


def _check_transactions(owner: str, txs: List[Dict[str, Any]], accounts_root: Optional[Path] = None) -> Dict[str, Any]:
    """Run compliance checks on a list of transactions."""

    warnings: List[str] = []
    approvals = load_approvals(owner, accounts_root)
    ucfg = load_user_config(owner, accounts_root)
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
                owner,
                month,
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
            logger.warning("invalid share count %r in transaction %s", raw_shares, t)
            shares = 0.0
        if action in {"buy", "purchase"}:
            last_buy[ticker] = d
            positions[ticker] += shares
        elif action == "sell":
            positions[ticker] -= shares
            acq = last_buy.get(ticker)
            if acq and (d - acq).days < (ucfg.hold_days_min or 0):
                days = (d - acq).days
                warnings.append(
                    f"Sold {ticker} after {days} days (min {ucfg.hold_days_min})"
                )
                logger.info(
                    "%s HOLD_DAYS_MIN %s %s",
                    datetime.now(UTC).isoformat(),
                    owner,
                    ticker,
                )

            meta = get_instrument_meta(ticker)
            instr_type = (
                meta.get("instrumentType") or meta.get("instrument_type") or ""
            ).upper()
            asset_class = (
                meta.get("assetClass") or meta.get("asset_class") or ""
            ).upper()
            sector = (meta.get("sector") or "").upper()
            is_commodity = asset_class == "COMMODITY" or sector == "COMMODITY"
            is_etf = instr_type == "ETF"
            exempt_type = instr_type in exempt_types
            if is_etf and is_commodity:
                exempt_type = False
            needs_approval = not (
                ticker in exempt_tickers
                or ticker.split(".")[0] in exempt_tickers
                or exempt_type
            )
            if needs_approval:
                appr = approvals.get(ticker) or approvals.get(ticker.split(".")[0])
                if not (appr and is_approval_valid(appr, d)):
                    warnings.append(f"Sold {ticker} without approval")
                    logger.info(
                        "%s APPROVAL_REQUIRED %s %s",
                        datetime.now(UTC).isoformat(),
                        owner,
                        ticker,
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
    txs = load_transactions(
        owner, accounts_root, scaffold_missing=scaffold_missing
    )
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
    txs = load_transactions(
        owner, accounts_root, scaffold_missing=scaffold_missing
    )
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
