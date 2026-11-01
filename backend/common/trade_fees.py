"""How a trade's ``fees`` breaks down into dealing, stamp duty and FX charges (#10493).

``fees`` is the *total* charge on a trade, as it always was: it is what
:mod:`backend.common.holdings_rebuild` adds to an acquisition's allowable cost
(and deducts from a disposal's proceeds). ``stamp_duty`` and ``fx_charge`` are
optional GBP breakdowns of that total, never added to it, so recording them
cannot change a cost basis and a charge already folded into ``fees`` by an
import is never counted twice. Whatever the breakdown does not explain is
dealing commission; a row with only ``fees`` (every row before #10493) is all
dealing.

A missing breakdown value is unknown, not 0 -- it simply leaves that part in
dealing.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, NamedTuple, Optional

FEE_BREAKDOWN_FIELDS = ("stamp_duty", "fx_charge")

# One penny of slack: pro-rating a split rounds each field to the penny on its
# own, so the parts can exceed the rounded total by that much.
BREAKDOWN_TOLERANCE_GBP = 0.01


class FeeSplit(NamedTuple):
    """A trade's ``fees`` split into its parts, all GBP and non-negative.

    ``fits`` is False when a recorded breakdown exceeded ``fees`` and was
    therefore ignored (everything counted as dealing).
    """

    dealing: float
    stamp_duty: float
    fx_charge: float
    fits: bool = True


def _amount(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def breakdown_error(fees: Any, stamp_duty: Any, fx_charge: Any) -> Optional[str]:
    """Why the breakdown is inconsistent with ``fees``, or ``None`` when it is fine."""
    parts = [_amount(value) for value in (stamp_duty, fx_charge)]
    if all(part is None for part in parts):
        return None
    total = _amount(fees)
    if total is None:
        return "fees is required when stamp_duty or fx_charge is set (fees is the total charge)"
    if sum(part or 0.0 for part in parts) > total + BREAKDOWN_TOLERANCE_GBP:
        return "stamp_duty plus fx_charge cannot exceed fees (fees is the total charge)"
    return None


def split_fees(tx: Mapping[str, Any]) -> Optional[FeeSplit]:
    """Split ``tx``'s ``fees``, or ``None`` when its fees are unknown.

    The magnitude of ``fees`` is used, as the all-in cost always has. A
    breakdown that does not fit within it (hand-edited data) is ignored and
    flagged with ``fits=False``, so the total counted is always ``fees`` once
    and the caller decides how to report it.
    """
    total = _amount(tx.get("fees"))
    if total is None:
        return None
    total = abs(total)
    stamp = abs(_amount(tx.get("stamp_duty")) or 0.0)
    fx = abs(_amount(tx.get("fx_charge")) or 0.0)
    if stamp + fx > total + BREAKDOWN_TOLERANCE_GBP:
        return FeeSplit(total, 0.0, 0.0, fits=False)
    return FeeSplit(max(total - stamp - fx, 0.0), stamp, fx)
