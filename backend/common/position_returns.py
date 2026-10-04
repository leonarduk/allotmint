"""Total return per held position: capital gain plus income received (#9038).

A holding's ``gain_gbp`` is capital only (market value vs. cost basis).  This
module adds, per position, from the account's transactions:

* ``income_gbp`` -- cash received from ``DIVIDEND``/``DIVIDENDS``/``INTEREST``
  rows for that instrument.  Income is counted as cash received; a dividend
  that was reinvested shows up as a separate ``BUY`` and is part of the cost
  basis, so it is not double counted.  Interest with no instrument (cash
  interest) belongs to no position and is ignored here.
* ``realised_gain_gbp`` -- the Section 104 gain on units of the instrument
  already sold, so a partly sold position's return includes what was banked.
* ``total_return_gbp`` -- ``gain_gbp + realised_gain_gbp + income_gbp``.
* ``total_return_pct`` -- ``total_return_gbp`` over all the cost ever put into
  the position (the cost still held plus the cost of the units sold).

``amount_minor`` is treated as GBP pence, as everywhere else that replays
transactions (see :mod:`backend.common.holdings_rebuild`).  When the account
has no transactions file every field is ``None``; when the capital gain or any
disposal's gain is unknown the total is ``None`` rather than a partial figure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from backend.common.holdings_rebuild import (
    CASH_TICKER,
    Disposal,
    _instrument_key,
    name_aliases,
    replay_transactions,
)

_INCOME_TYPES = {"DIVIDEND", "DIVIDENDS", "INTEREST"}
_EPS = 1e-9

TOTAL_RETURN_FIELDS = ("income_gbp", "realised_gain_gbp", "total_return_gbp", "total_return_pct")


@dataclass
class PositionReturn:
    """Income and realised figures for one instrument pool."""

    income_gbp: float = 0.0
    realised_gain_gbp: float = 0.0
    disposed_cost_gbp: float = 0.0
    realised_known: bool = True


def _amount_gbp(tx: Mapping[str, Any]) -> Optional[float]:
    try:
        value = float(tx.get("amount_minor"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if value != value else abs(value) / 100.0


def position_returns(transactions: Sequence[Mapping[str, Any]]) -> Dict[str, PositionReturn]:
    """Return income and realised gains keyed by instrument pool key.

    Keys match :func:`backend.common.holdings_rebuild.transaction_cost_hints`
    (canonical tickers, or ``name:``/``ref:`` keys for unresolved rows).
    """
    rows = [tx for tx in transactions if isinstance(tx, Mapping)]
    aliases = name_aliases(rows)
    results: Dict[str, PositionReturn] = {}

    for tx in rows:
        if str(tx.get("type") or "").upper() not in _INCOME_TYPES:
            continue
        key = _instrument_key(tx, aliases)
        amount = _amount_gbp(tx)
        if key is None or key == CASH_TICKER or amount is None:
            continue
        results.setdefault(key, PositionReturn()).income_gbp += amount

    def record(disposal: Disposal) -> None:
        if disposal.tx_type != "SELL":
            return
        key = _instrument_key(rows[disposal.index], aliases)
        if key is None:
            return
        entry = results.setdefault(key, PositionReturn())
        entry.disposed_cost_gbp += disposal.cost_gbp
        unmatched = disposal.unknown_cost_units + disposal.unmatched_units
        if disposal.proceeds_gbp is None or unmatched > _EPS:
            entry.realised_known = False
        else:
            entry.realised_gain_gbp += disposal.proceeds_gbp - disposal.cost_gbp

    _ = replay_transactions(rows, aliases=aliases, on_disposal=record, warn=False)
    return results


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if result != result else result


def apply_total_return(holding: Dict[str, Any], entry: Optional[PositionReturn]) -> None:
    """Set the total-return fields on an enriched ``holding`` in place."""
    entry = entry or PositionReturn()
    income = round(entry.income_gbp, 2)
    realised = round(entry.realised_gain_gbp, 2) if entry.realised_known else None
    holding["income_gbp"] = income
    holding["realised_gain_gbp"] = realised

    gain = _float_or_none(holding.get("gain_gbp"))
    market = _float_or_none(holding.get("market_value_gbp"))
    if gain is None or market is None or realised is None:
        holding["total_return_gbp"] = None
        holding["total_return_pct"] = None
        return
    total = round(gain + realised + income, 2)
    invested = (market - gain) + entry.disposed_cost_gbp
    holding["total_return_gbp"] = total
    holding["total_return_pct"] = total / invested * 100.0 if invested > _EPS else None


def clear_total_return(holding: Dict[str, Any]) -> None:
    """Mark the total-return fields unknown (no transactions to derive them from)."""
    for key in TOTAL_RETURN_FIELDS:
        holding[key] = None


def attach_total_returns(
    holdings: List[Dict[str, Any]],
    transactions: Optional[Sequence[Mapping[str, Any]]],
    match_key: Callable[[str, List[str]], Optional[str]],
) -> None:
    """Attach total-return fields to every non-cash enriched holding.

    ``match_key(ticker, pool_keys)`` maps a held ticker to its pool key (or
    ``None``); it is injected so callers can reuse their own matching rules.
    """
    returns = position_returns(transactions) if transactions is not None else None
    pool_keys = [k for k in (returns or {}) if not k.startswith(("name:", "ref:"))]
    for h in holdings:
        if not isinstance(h, dict):
            continue
        ticker = str(h.get("ticker") or "").strip().upper()
        if not ticker or ticker.split(".", 1)[0] == "CASH":
            continue
        if returns is None:
            clear_total_return(h)
            continue
        key = match_key(ticker, pool_keys)
        apply_total_return(h, returns.get(key) if key else None)
