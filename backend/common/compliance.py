from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any

from backend.common.constants import MAX_TRADES_PER_MONTH, HOLD_DAYS_MIN

_DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "accounts"


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val).date()
    except Exception:
        return None


def load_transactions(owner: str) -> List[Dict[str, Any]]:
    """Load all transactions for ``owner`` sorted by date.

    Raises
    ------
    FileNotFoundError
        If the owner's directory does not exist.
    """
    owner_dir = _DATA_ROOT / owner
    if not owner_dir.exists():
        raise FileNotFoundError(owner)

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


def check_owner(owner: str) -> Dict[str, Any]:
    """Return compliance warnings for an owner."""
    txs = load_transactions(owner)
    warnings: List[str] = []

    # trade count rule
    counts: Dict[str, int] = defaultdict(int)
    for t in txs:
        d = _parse_date(t.get("date"))
        if not d:
            continue
        key = f"{d.year:04d}-{d.month:02d}"
        counts[key] += 1
    for month, cnt in counts.items():
        if cnt > MAX_TRADES_PER_MONTH:
            warnings.append(f"{cnt} trades in {month} (max {MAX_TRADES_PER_MONTH})")

    # holding period rule
    last_buy: Dict[str, date] = {}
    for t in txs:
        d = _parse_date(t.get("date"))
        if not d:
            continue
        ticker = (t.get("ticker") or "").upper()
        action = (t.get("type") or t.get("kind") or "").lower()
        if action in {"buy", "purchase"}:
            last_buy[ticker] = d
        elif action == "sell":
            acq = last_buy.get(ticker)
            if acq and (d - acq).days < HOLD_DAYS_MIN:
                days = (d - acq).days
                warnings.append(
                    f"Sold {ticker} after {days} days (min {HOLD_DAYS_MIN})"
                )
    return {"owner": owner, "warnings": warnings, "trade_counts": dict(counts)}
