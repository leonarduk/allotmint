"""Helpers to reconcile account holdings with transaction history."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Mapping

from backend.common.data_loader import resolve_paths
from backend.config import config

logger = logging.getLogger(__name__)


_METADATA_STEMS = {"person", "config", "notes"}
_TYPE_SIGN = {
    "BUY": 1.0,
    "PURCHASE": 1.0,
    "TRANSFER_IN": 1.0,
    "SELL": -1.0,
    "TRANSFER_OUT": -1.0,
    "REMOVAL": -1.0,
}
_SHARE_SCALE = 10**8


def _normalise_account_key(raw: str | None, fallback: str) -> str:
    value = (raw or fallback).strip()
    return value.lower()


def _load_json(path: Path) -> Mapping[str, object] | None:
    try:
        text = path.read_text()
    except OSError as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON in %s: %s", path, exc)
        return None


def _transactions_to_positions(transactions: Iterable[Mapping[str, object]]) -> Mapping[str, float]:
    ledger: defaultdict[str, float] = defaultdict(float)
    for tx in transactions:
        t_type = (str(tx.get("type") or tx.get("kind") or "")).upper()
        ticker = (str(tx.get("ticker") or "")).upper()
        if not ticker or t_type not in _TYPE_SIGN:
            continue

        raw_qty = (
            tx.get("shares")
            if tx.get("shares") is not None
            else tx.get("units")
            if tx.get("units") is not None
            else tx.get("quantity")
        )
        try:
            qty = float(raw_qty or 0.0)
        except (TypeError, ValueError):
            logger.debug("Skipping transaction with invalid quantity: %s", tx)
            continue

        if abs(qty) > 1_000_000:
            qty /= _SHARE_SCALE

        ledger[ticker] += qty * _TYPE_SIGN[t_type]

    return ledger


def reconcile_transactions_with_holdings(accounts_root: Path | None = None) -> None:
    """Ensure each holding balance is reproducible from transactions.

    Synthetic balancing transactions are injected when a holding's share
    count cannot be explained by the recorded buys and sells.  The synthetic
    entries are timestamped one year in the past and marked with
    ``{"synthetic": True}`` so downstream consumers can differentiate them.
    """

    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = Path(accounts_root) if accounts_root else paths.accounts_root

    if not root.exists():
        return

    synthetic_date = (date.today() - timedelta(days=365)).isoformat()

    for owner_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        tx_candidates = {}
        for candidate in owner_dir.glob("*_transactions.json"):
            stem = candidate.stem.replace("_transactions", "")
            tx_candidates[stem.lower()] = candidate

        for account_file in owner_dir.glob("*.json"):
            stem = account_file.stem
            lower = stem.lower()
            if lower in _METADATA_STEMS or lower.endswith("_transactions"):
                continue

            account_data = _load_json(account_file)
            if not account_data:
                continue

            account_key = _normalise_account_key(account_data.get("account_type"), stem)
            tx_path = tx_candidates.get(account_key)
            if not tx_path:
                continue

            tx_data = _load_json(tx_path)
            if tx_data is None:
                continue

            transactions = list(tx_data.get("transactions") or [])
            if not transactions and not account_data.get("holdings"):
                continue

            ledger = _transactions_to_positions(transactions)

            holdings_raw = account_data.get("holdings") or []
            holdings: dict[str, float] = {}
            for item in holdings_raw:
                ticker = (str(item.get("ticker") or "")).upper()
                if not ticker:
                    continue
                try:
                    qty = float(item.get("units") or 0.0)
                except (TypeError, ValueError):
                    logger.debug("Skipping holding with invalid units: %s", item)
                    continue
                holdings[ticker] = qty

            adjustments: list[dict[str, object]] = []

            # First align holdings we expect to see.
            for ticker, target_qty in holdings.items():
                diff = target_qty - ledger.get(ticker, 0.0)
                if abs(diff) <= 1e-6:
                    continue
                adjustments.append(
                    {
                        "date": synthetic_date,
                        "ticker": ticker,
                        "type": "BUY" if diff > 0 else "SELL",
                        "shares": abs(diff),
                        "units": abs(diff),
                        "synthetic": True,
                    }
                )

            # Then remove any stray positions that exist only in transactions.
            for ticker, qty in ledger.items():
                if ticker in holdings:
                    continue
                if abs(qty) <= 1e-6:
                    continue
                adjustments.append(
                    {
                        "date": synthetic_date,
                        "ticker": ticker,
                        "type": "SELL" if qty > 0 else "BUY",
                        "shares": abs(qty),
                        "units": abs(qty),
                        "synthetic": True,
                    }
                )

            if not adjustments:
                continue

            logger.info(
                "Injecting %d synthetic transaction(s) for %s/%s", len(adjustments), owner_dir.name, stem
            )

            transactions.extend(adjustments)
            tx_data["transactions"] = transactions

            try:
                tx_path.write_text(json.dumps(tx_data, indent=2) + "\n")
            except OSError as exc:
                logger.warning("Failed to update %s: %s", tx_path, exc)

