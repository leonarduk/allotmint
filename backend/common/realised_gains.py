"""Realised gain/loss per disposal using UK Section 104 average-cost pooling.

Each instrument within an ``(owner, account)`` keeps a single pool of units and
their total allowable cost.  Acquisitions add to the pool; a SELL takes cost
out of the pool pro rata and its realised gain is ``proceeds - cost``.

Transactions are replayed in date order with acquisitions before disposals on
the same day, which approximates HMRC's same-day matching rule.

Units that enter the pool without a known cost (e.g. a ``TRANSFER_IN`` for a
position held before the records begin) make any disposal drawing on them
indeterminate: ``realised_gain_gbp`` is ``None`` and ``unmatched_units``
reports how many of the units sold had no known cost.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

_ACQUIRE = {"BUY", "PURCHASE", "TRANSFER_IN"}
_DISPOSE = {"SELL", "TRANSFER_OUT", "REMOVAL"}
_SHARE_SCALE = 10**8
_EPS = 1e-9


@dataclass(frozen=True)
class DisposalGain:
    """Result for a single disposal transaction."""

    cost_basis_gbp: float
    proceeds_gbp: float | None
    realised_gain_gbp: float | None
    unmatched_units: float


@dataclass
class _Pool:
    units: float = 0.0
    cost: float = 0.0
    unknown_cost_units: float = 0.0


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN
        return None
    return result


def _quantity(tx: Mapping[str, Any]) -> float | None:
    for key in ("units", "shares", "quantity"):
        qty = _float(tx.get(key))
        if qty is not None:
            qty = abs(qty)
            return qty / _SHARE_SCALE if qty > 1_000_000 else qty
    return None


def _cash_value(tx: Mapping[str, Any], qty: float, *, acquisition: bool) -> float | None:
    """Settled GBP value: ``amount_minor`` if present, else price x units -/+ fees."""
    amount_minor = _float(tx.get("amount_minor"))
    if amount_minor is not None:
        return abs(amount_minor) / 100.0
    price = _float(tx.get("price_gbp"))
    if price is None:
        return None
    fees = _float(tx.get("fees")) or 0.0
    gross = price * qty
    return gross + fees if acquisition else gross - fees


def _instrument_key(tx: Mapping[str, Any]) -> str | None:
    for key in ("ticker", "security_ref", "instrument_name"):
        value = tx.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return None


def compute_disposal_gains(transactions: Sequence[Mapping[str, Any]]) -> dict[int, DisposalGain]:
    """Return realised gain results keyed by index into ``transactions``.

    ``transactions`` must all belong to one ``(owner, account)``.  Only
    disposals of a known instrument and quantity appear in the result;
    ``TRANSFER_OUT``/``REMOVAL`` reduce the pool without realising a gain.
    """
    order = sorted(
        range(len(transactions)),
        key=lambda i: (
            str(transactions[i].get("date") or "")[:10],
            0 if str(transactions[i].get("type") or "").upper() in _ACQUIRE else 1,
            i,
        ),
    )

    pools: defaultdict[str, _Pool] = defaultdict(_Pool)
    results: dict[int, DisposalGain] = {}

    for idx in order:
        tx = transactions[idx]
        tx_type = str(tx.get("type") or "").upper()
        if tx_type not in _ACQUIRE and tx_type not in _DISPOSE:
            continue
        key = _instrument_key(tx)
        qty = _quantity(tx)
        if key is None or not qty:
            continue
        pool = pools[key]

        if tx_type in _ACQUIRE:
            cost = _cash_value(tx, qty, acquisition=True)
            pool.units += qty
            if cost is None:
                pool.unknown_cost_units += qty
            else:
                pool.cost += cost
            continue

        matched = min(qty, pool.units)
        fraction = matched / pool.units if pool.units > _EPS else 0.0
        cost_out = pool.cost * fraction
        unknown_out = pool.unknown_cost_units * fraction
        pool.units -= matched
        pool.cost -= cost_out
        pool.unknown_cost_units -= unknown_out
        if pool.units <= _EPS:
            pools[key] = _Pool()

        if tx_type != "SELL":
            continue

        unmatched = unknown_out + (qty - matched)
        proceeds = _cash_value(tx, qty, acquisition=False)
        gain = None
        if proceeds is not None and unmatched <= _EPS:
            gain = round(proceeds - cost_out, 2)
        results[idx] = DisposalGain(
            cost_basis_gbp=round(cost_out, 2),
            proceeds_gbp=None if proceeds is None else round(proceeds, 2),
            realised_gain_gbp=gain,
            unmatched_units=round(unmatched, 6) if unmatched > _EPS else 0.0,
        )

    return results
