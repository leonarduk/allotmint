"""Utilities to update account holdings from broker CSV exports."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, List, Mapping

from backend import importers
from backend.common.path_utils import safe_join
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)


def _to_holding(tx: Any) -> dict[str, object]:
    cost = (tx.amount_minor or 0.0) / 100.0 if tx.amount_minor is not None else 0.0
    holding: dict[str, object] = {
        "ticker": tx.ticker,
        "units": tx.units or 0.0,
        "cost_basis_gbp": cost,
    }
    if tx.price is not None:
        holding["current_price_gbp"] = tx.price
    return holding


def _normalise_ticker(ticker: object, provider: str) -> str:
    """Return the canonical ticker used by stored holdings."""
    value = str(ticker or "").strip().upper()
    if value in {"CASH", "GBP", "CASH GBP", "CASH.GBP"}:
        return "CASH.GBP"
    if provider.lower() == "hargreaves" and value and "." not in value:
        return f"{value}.L"
    return value


def _number(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _normalise_holding(holding: Mapping[str, object], provider: str) -> dict[str, float | str]:
    units = _number(holding.get("units"))
    price = _number(holding.get("current_price_gbp", holding.get("price_gbp", holding.get("price"))))
    explicit_value = holding.get("value_gbp", holding.get("market_value_gbp"))
    value = _number(explicit_value) if explicit_value is not None else units * price
    ticker = _normalise_ticker(holding.get("ticker"), provider)
    if ticker == "CASH.GBP" and value == 0.0:
        value = units
    return {"ticker": ticker, "units": units, "value_gbp": value}


def _index_holdings(holdings: List[Mapping[str, object]], provider: str) -> dict[str, dict[str, float | str]]:
    indexed: dict[str, dict[str, float | str]] = {}
    for raw in holdings:
        normalised = _normalise_holding(raw, provider)
        ticker = str(normalised["ticker"])
        if not ticker:
            continue
        existing = indexed.setdefault(ticker, {"ticker": ticker, "units": 0.0, "value_gbp": 0.0})
        existing["units"] = float(existing["units"]) + float(normalised["units"])
        existing["value_gbp"] = float(existing["value_gbp"]) + float(normalised["value_gbp"])
    return indexed


def reconcile_from_csv(
    provider: str,
    data: bytes,
    stored_holdings: List[Mapping[str, object]],
) -> dict[str, object]:
    """Compare a broker export with stored holdings without modifying either."""
    logger.info("reconcile from csv - Provider %s", sanitise_log_value(provider))

    transactions: List[Any] = importers.parse(provider, data)
    imported = _index_holdings([_to_holding(tx) for tx in transactions if tx.ticker], provider)
    stored = _index_holdings(stored_holdings, provider)
    cash_ticker = "CASH.GBP"
    imported_cash = float(imported.pop(cash_ticker, {}).get("value_gbp", 0.0))
    stored_cash = float(stored.pop(cash_ticker, {}).get("value_gbp", 0.0))

    added = [imported[ticker] for ticker in sorted(imported.keys() - stored.keys())]
    removed = [stored[ticker] for ticker in sorted(stored.keys() - imported.keys())]
    quantity_changed: list[dict[str, float | str]] = []
    value_changed: list[dict[str, float | str]] = []
    for ticker in sorted(imported.keys() & stored.keys()):
        before = stored[ticker]
        after = imported[ticker]
        old_units, new_units = float(before["units"]), float(after["units"])
        old_value, new_value = float(before["value_gbp"]), float(after["value_gbp"])
        if abs(new_units - old_units) > 1e-9:
            quantity_changed.append(
                {
                    "ticker": ticker,
                    "stored_units": old_units,
                    "imported_units": new_units,
                    "delta": new_units - old_units,
                }
            )
        if abs(new_value - old_value) > 0.005:
            value_changed.append(
                {
                    "ticker": ticker,
                    "stored_value_gbp": round(old_value, 2),
                    "imported_value_gbp": round(new_value, 2),
                    "delta_gbp": round(new_value - old_value, 2),
                }
            )

    return {
        "added": added,
        "removed": removed,
        "quantity_changed": quantity_changed,
        "value_changed": value_changed,
        "cash_balance": {
            "stored_gbp": round(stored_cash, 2),
            "imported_gbp": round(imported_cash, 2),
            "delta_gbp": round(imported_cash - stored_cash, 2),
        },
    }


def _aggregate_for_storage(raw_holdings: List[Mapping[str, object]], provider: str) -> List[dict[str, object]]:
    """Collapse per-row parsed holdings into one entry per ticker.

    Reuses :func:`_index_holdings` (the same aggregation reconcile relies on)
    for ``units``/``value_gbp`` so a CSV with more than one row for a ticker
    (e.g. a repeated cash line) produces a single position instead of
    duplicates. ``cost_basis_gbp`` is summed separately since reconcile's
    diff output has no use for it and ``_index_holdings`` doesn't carry it.
    """
    indexed = _index_holdings(raw_holdings, provider)
    cost_basis_gbp: dict[str, float] = {}
    for raw in raw_holdings:
        ticker = _normalise_ticker(raw.get("ticker"), provider)
        if ticker not in indexed:
            continue
        cost_basis_gbp[ticker] = cost_basis_gbp.get(ticker, 0.0) + _number(raw.get("cost_basis_gbp"))

    return [
        {
            "ticker": ticker,
            "units": indexed[ticker]["units"],
            "value_gbp": round(float(indexed[ticker]["value_gbp"]), 2),
            "cost_basis_gbp": round(cost_basis_gbp.get(ticker, 0.0), 2),
        }
        for ticker in sorted(indexed)
    ]


def update_from_csv(
    owner: str,
    account: str,
    provider: str,
    data: bytes,
) -> dict[str, str]:
    """Parse ``data`` from ``provider`` and update ``owner``/``account`` holdings.

    Merges the parsed holdings into the existing stored document (preserving
    any other fields already on it) rather than overwriting it wholesale.
    Returns a mapping containing the path to the written holdings file. A
    dictionary is returned instead of a plain string so callers (and tests)
    can easily extend the response with additional metadata in the future
    without changing the return type again.
    """

    transactions: List[Any] = importers.parse(provider, data)
    raw_holdings = [_to_holding(t) for t in transactions if t.ticker]
    holdings = _aggregate_for_storage(raw_holdings, provider)

    try:
        base_dir = safe_join(Path(config.accounts_root), owner)
        acct_path = safe_join(base_dir, f"{account}.json")
    except ValueError as exc:
        raise ValueError(f"Invalid path component: {exc}") from exc

    existing: dict[str, Any] = {}
    if acct_path.exists():
        try:
            loaded = json.loads(acct_path.read_text())
        except (OSError, json.JSONDecodeError):
            logger.warning("Failed to read existing holdings at %s; overwriting", sanitise_log_value(acct_path))
        else:
            if isinstance(loaded, dict):
                existing = loaded

    payload = {
        **existing,
        "owner": owner,
        "account_type": account,
        "currency": existing.get("currency", "GBP"),
        "last_updated": date.today().isoformat(),
        "holdings": holdings,
    }

    base_dir.mkdir(parents=True, exist_ok=True)
    acct_path.write_text(json.dumps(payload, indent=2))

    return {"path": str(acct_path)}
