"""All-in annual cost in GBP: fund ongoing charges plus costs actually paid (#10482).

Two parts, per account and in total:

* **Fund charges** -- each priced, non-cash holding's ``ongoing_charge_pct``
  (see :mod:`backend.common.fund_charges`) applied to its current value. A
  holding with no usable charge is *unknown*: its value is reported in
  ``unknown_value_gbp`` and it adds nothing to the cost, so a missing figure is
  never counted as GBP 0.
* **Transaction costs** over the last 12 months -- the ``fees`` recorded on
  trades (dealing commission; stamp duty and FX charges are included where the
  import folds them into ``fees``, as no separate field exists) plus account
  charges (``FEES`` rows, less ``FEES_REFUND`` rows). A trade with no ``fees``
  value is counted in ``trades_without_fee_data``: its cost is unknown, not 0.

``FEES``/``FEES_REFUND`` rows carry ``amount_minor`` (pence); trade ``fees``
are GBP, as :mod:`backend.common.holdings_rebuild` reads them.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional

from backend.common.fund_charges import ongoing_charge_pct
from backend.common.sector_labels import is_cash_instrument

WINDOW_DAYS = 365
_TRADE_TYPES = {"BUY", "PURCHASE", "SELL"}
_ACCOUNT_CHARGE_SIGNS = {"FEES": 1, "FEES_REFUND": -1}


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _empty_part() -> Dict[str, Any]:
    return {
        "value_gbp": 0.0,
        "fund_charges_gbp": 0.0,
        "known_value_gbp": 0.0,
        "unknown_value_gbp": 0.0,
        "holding_count": 0,
        "unknown_count": 0,
        "dealing_fees_gbp": 0.0,
        "account_charges_gbp": 0.0,
        "trade_count": 0,
        "trades_without_fee_data": 0,
    }


def _add_holdings(part: Dict[str, Any], holdings: Iterable[Mapping[str, Any]]) -> None:
    for holding in holdings:
        value = _number(holding.get("market_value_gbp"))
        if value is None or value <= 0:
            continue
        part["value_gbp"] += value
        if is_cash_instrument(holding.get("ticker"), holding.get("instrument_type")):
            continue
        part["holding_count"] += 1
        charge = ongoing_charge_pct(holding)
        if charge is None:
            part["unknown_count"] += 1
            part["unknown_value_gbp"] += value
            continue
        part["known_value_gbp"] += value
        part["fund_charges_gbp"] += value * charge / 100.0


def _in_window(raw: Any, start: date, end: date) -> bool:
    try:
        day = date.fromisoformat(str(raw)[:10])
    except ValueError:
        return False
    return start <= day <= end


def _add_transaction(part: Dict[str, Any], tx: Mapping[str, Any]) -> None:
    tx_type = str(tx.get("type") or "").upper()
    if tx_type in _TRADE_TYPES:
        part["trade_count"] += 1
        fees = _number(tx.get("fees"))
        if fees is None:
            part["trades_without_fee_data"] += 1
        else:
            part["dealing_fees_gbp"] += abs(fees)
        return
    sign = _ACCOUNT_CHARGE_SIGNS.get(tx_type)
    amount = _number(tx.get("amount_minor"))
    if sign is not None and amount is not None:
        part["account_charges_gbp"] += sign * abs(amount) / 100.0


def _finish(part: Dict[str, Any]) -> Dict[str, Any]:
    known_cost = part["fund_charges_gbp"] + part["dealing_fees_gbp"] + part["account_charges_gbp"]
    value = part["value_gbp"]
    out = {key: (round(v, 2) if isinstance(v, float) else v) for key, v in part.items()}
    # No known charge at all is "unknown", not GBP 0 (#7834).
    out["fund_charges_gbp"] = round(part["fund_charges_gbp"], 2) if part["known_value_gbp"] > 0 else None
    out["known_cost_gbp"] = round(known_cost, 2)
    out["known_cost_pct"] = round(known_cost / value * 100.0, 4) if value > 0 else None
    out["complete"] = part["unknown_count"] == 0 and part["trades_without_fee_data"] == 0
    return out


def compute_all_in_cost(
    portfolio: Mapping[str, Any],
    transactions: Iterable[Mapping[str, Any]],
    *,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """All-in annual cost of ``portfolio`` (owner or group) from its holdings and ``transactions``.

    Transactions are matched to accounts by ``(owner, account)`` when the
    account carries an owner (group portfolios), else by account alone;
    costs for an account no longer held still count, under their own row.
    """
    end = today or date.today()
    start = end - timedelta(days=WINDOW_DAYS)
    parts: Dict[tuple, Dict[str, Any]] = {}
    labels: Dict[tuple, Dict[str, Any]] = {}
    for account in portfolio.get("accounts") or []:
        key = (str(account.get("owner") or "").lower(), str(account.get("account_type") or "").lower())
        labels.setdefault(key, {"owner": account.get("owner"), "account": account.get("account_type")})
        _add_holdings(parts.setdefault(key, _empty_part()), account.get("holdings") or [])
    owners = {k[0] for k in parts if k[0]}
    for tx in transactions:
        if not _in_window(tx.get("date"), start, end):
            continue
        owner = str(tx.get("owner") or "").lower() if owners else ""
        key = (owner, str(tx.get("account") or "").lower())
        labels.setdefault(key, {"owner": tx.get("owner") if owners else None, "account": tx.get("account")})
        _add_transaction(parts.setdefault(key, _empty_part()), tx)
    total = _empty_part()
    for part in parts.values():
        for name, value in part.items():
            total[name] += value
    accounts: List[Dict[str, Any]] = [{**labels[key], **_finish(part)} for key, part in parts.items()]
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "accounts": sorted(accounts, key=lambda row: -row["value_gbp"]),
        "total": _finish(total),
    }
