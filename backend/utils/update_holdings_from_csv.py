"""Utilities to update account holdings from broker CSV exports."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, List, Mapping

from backend import importers
from backend.common.instruments import resolve_instrument_ticker
from backend.common.path_utils import safe_join
from backend.common.ticker_utils import canonical_ticker
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

_CASH_TICKER = "CASH.GBP"


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
        # Resolution is metadata-only here: importing a CSV must never block on
        # one network call per holding.  The explicit ticker reconciliation
        # command persists discoveries, so subsequent imports use them freely.
        resolved = resolve_instrument_ticker(value)
        if resolved is None:
            logger.warning(
                "No persisted metadata for bare Hargreaves ticker %s; defaulting to .L. "
                "Run scripts/reconcile_holding_tickers.py --write if this is a foreign holding.",
                sanitise_log_value(value),
            )
            return f"{value}.L"
        return resolved
    # HL exports padded two-letter LSE EPICs as "BP."; store them as "BP.L"
    # rather than with an empty exchange (#8600).
    return canonical_ticker(value)


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
    stored_cash = float(stored.pop(_CASH_TICKER, {}).get("value_gbp", 0.0))
    # A CSV without a cash line leaves stored cash unchanged on import (#10906),
    # so the preview must not report it as a cash withdrawal.
    imported_cash = float(imported.pop(_CASH_TICKER, {"value_gbp": stored_cash})["value_gbp"])

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


def _distribute(total: float, weights: List[float]) -> List[float]:
    """Split ``total`` across ``weights`` in proportion, rounded to pence.

    The last share absorbs the rounding residue so the parts sum to ``total``.
    Zero total weight puts everything on the last part.
    """
    weight_sum = sum(weights)
    if weight_sum <= 0:
        return [0.0] * (len(weights) - 1) + [round(total, 2)]
    shares = [round(total * weight / weight_sum, 2) for weight in weights[:-1]]
    return [*shares, round(total - sum(shares), 2)]


def _resize_lots(lots: List[dict[str, Any]], target_units: float) -> List[dict[str, Any]]:
    """Bring the lots' total units to ``target_units`` keeping earlier lots intact.

    An increase is added to the last (most recently listed) lot; a decrease is
    taken from the last lots first and lots that reach zero are dropped, so the
    oldest ``acquired_date`` values survive. At least one lot is always kept,
    and a negative target is treated as zero.
    """
    target_units = max(target_units, 0.0)
    excess = sum(_number(lot.get("units")) for lot in lots) - target_units
    kept = list(lots)
    while excess > 1e-9 and len(kept) > 1 and _number(kept[-1].get("units")) <= excess + 1e-9:
        excess -= _number(kept.pop().get("units"))
    others = sum(_number(lot.get("units")) for lot in kept[:-1])
    kept[-1]["units"] = target_units - others
    return kept


def _apply_import_to_lots(lots: List[dict[str, Any]], update: Mapping[str, object]) -> List[dict[str, Any]]:
    """Update a ticker's stored lots from the imported totals, keeping other fields.

    ``units``/``value_gbp``/``cost_basis_gbp`` come from the CSV; everything
    else on each lot (``acquired_date`` and the like) is preserved (#10906).
    Cost is split in proportion to the lots' existing cost (units as fallback).
    """
    kept = _resize_lots(lots, _number(update.get("units")))
    units = [_number(lot.get("units")) for lot in kept]
    costs = [_number(lot.get("cost_basis_gbp")) for lot in kept]
    values = _distribute(_number(update.get("value_gbp")), units)
    new_costs = _distribute(_number(update.get("cost_basis_gbp")), costs if sum(costs) > 0 else units)
    for lot, value, cost in zip(kept, values, new_costs):
        lot["value_gbp"] = value
        lot["cost_basis_gbp"] = cost
    return kept


def _group_stored_lots(stored: List[object], provider: str) -> dict[str, List[dict[str, Any]]]:
    """Group stored holdings by canonical ticker, preserving stored order."""
    grouped: dict[str, List[dict[str, Any]]] = {}
    for raw in stored:
        if not isinstance(raw, Mapping):
            logger.warning("Dropping malformed stored holding during CSV import: %s", sanitise_log_value(raw))
            continue
        ticker = _normalise_ticker(raw.get("ticker"), provider)
        grouped.setdefault(ticker, []).append(dict(raw))
    return grouped


def _merge_holdings(stored: List[object], imported: List[dict[str, object]], provider: str) -> List[dict[str, Any]]:
    """Merge imported per-ticker totals into the stored holdings (#10906).

    Matches :func:`reconcile_from_csv`: tickers in both are updated in place,
    new tickers are appended (with no ``acquired_date``), and stored tickers
    the CSV omits are removed -- except cash, which stays unchanged unless the
    CSV reports a cash line.
    """
    imported_by_ticker = {str(holding["ticker"]): holding for holding in imported}
    merged: List[dict[str, Any]] = []
    grouped = _group_stored_lots(stored, provider)
    for ticker, lots in grouped.items():
        update = imported_by_ticker.get(ticker)
        if update is not None:
            merged.extend(_apply_import_to_lots(lots, update))
        elif ticker == _CASH_TICKER:
            merged.extend(lots)
    merged.extend(imported_by_ticker[ticker] for ticker in sorted(imported_by_ticker.keys() - grouped.keys()))
    return merged


def update_from_csv(
    owner: str,
    account: str,
    provider: str,
    data: bytes,
) -> dict[str, str]:
    """Parse ``data`` from ``provider`` and update ``owner``/``account`` holdings.

    Merges the parsed holdings into the existing stored document per ticker
    (see :func:`_merge_holdings`), preserving any other fields already on the
    document and on each holding, including ``account_type`` casing (#10906).
    Returns a mapping containing the path to the written holdings file. A
    dictionary is returned instead of a plain string so callers (and tests)
    can easily extend the response with additional metadata in the future
    without changing the return type again.
    """

    transactions: List[Any] = importers.parse(provider, data)
    raw_holdings = [_to_holding(t) for t in transactions if t.ticker]
    imported = _aggregate_for_storage(raw_holdings, provider)

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

    stored_holdings = existing.get("holdings")
    payload = {
        **existing,
        "owner": owner,
        "account_type": existing.get("account_type") or account,
        "currency": existing.get("currency", "GBP"),
        "last_updated": date.today().isoformat(),
        "holdings": _merge_holdings(stored_holdings if isinstance(stored_holdings, list) else [], imported, provider),
    }

    base_dir.mkdir(parents=True, exist_ok=True)
    acct_path.write_text(json.dumps(payload, indent=2))

    return {"path": str(acct_path)}
