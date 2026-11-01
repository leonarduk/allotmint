"""Defaults the monitor reads from the owner's other records (#10510).

* **Contributions**: the annual total of the owner's recorded contribution
  schedule (#10479, :mod:`backend.allowance_guardian.schedule`), used when the
  run's settings give no ``contribution_annual``.
* **Fees**: the all-in annual cost of the owner's DC pension accounts (#10482,
  :mod:`backend.fund_upkeep.all_in_cost`) as a % of their value, used when the
  settings give no ``fee_pct``.

Both are optional: with no schedule or no usable cost the monitor runs as
before (no contribution, gross returns). Nothing here writes any data. Only
accounts that count towards the forecast's pot
(:data:`backend.common.pension.DEFINED_CONTRIBUTION_ACCOUNT_MARKERS`) are used,
so the defaults describe the same pot that is simulated.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from pydantic import ValidationError

from backend.allowance_guardian.schedule import ScheduledContribution, load_schedule
from backend.common.pension import DEFINED_CONTRIBUTION_ACCOUNT_MARKERS
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

PAYMENTS_PER_YEAR = {"monthly": 12, "quarterly": 4, "annual": 1}


@dataclass
class Resolved:
    """A resolved input: its value (``None`` = not available), where it came from, and notes for the report."""

    value: Optional[float]
    source: Optional[str]
    notes: list[str] = field(default_factory=list)


def _is_dc_account(account: Any) -> bool:
    name = str(account or "").lower()
    return any(marker in name for marker in DEFINED_CONTRIBUTION_ACCOUNT_MARKERS)


def _active(item: ScheduledContribution, on: dt.date) -> bool:
    return item.start_date <= on and (item.end_date is None or item.end_date >= on)


def schedule_annual_gbp(contributions: Iterable[ScheduledContribution], on: dt.date) -> tuple[float, int]:
    """(GBP a year paid into DC pension accounts, entries counted) for entries active on ``on``.

    Relief-at-source payments count gross (``allowance_minor``), since the
    provider adds the relief to the pot.
    """
    total_minor = 0
    counted = 0
    for item in contributions:
        if not item.is_pension or not _is_dc_account(item.account) or not _active(item, on):
            continue
        total_minor += item.allowance_minor() * PAYMENTS_PER_YEAR[item.frequency]
        counted += 1
    return total_minor / 100.0, counted


def scheduled_contribution(owner: str, data_root: Path, on: dt.date) -> Resolved:
    """The recorded schedule's annual total, or ``Resolved(None, ...)`` when there is none to use."""
    try:
        schedule = load_schedule(owner, data_root)
    except (ValidationError, ValueError, OSError) as exc:
        logger.warning("Contribution schedule unreadable for the readiness run: %s", sanitise_log_value(exc))
        return Resolved(
            None, None, ["The recorded contribution schedule could not be read, so no contribution is assumed."]
        )
    annual, counted = schedule_annual_gbp(schedule.contributions, on)
    if not counted:
        return Resolved(None, None)
    note = (
        f"Annual contribution of £{annual:,.2f} taken from the recorded contribution schedule "
        f"({counted} current DC pension entr{'y' if counted == 1 else 'ies'}, relief at source added)."
    )
    return Resolved(annual, "schedule", [note])


def _as_mapping(tx: Any) -> Mapping[str, Any]:
    if isinstance(tx, Mapping):
        return tx
    dump = getattr(tx, "model_dump", None)
    return dump() if callable(dump) else vars(tx)


def dc_fee_pct(all_in: Mapping[str, Any]) -> Resolved:
    """Known all-in cost of the DC pension accounts as a % of their value, from ``compute_all_in_cost``'s result."""
    rows = [row for row in all_in.get("accounts") or [] if _is_dc_account(row.get("account"))]
    value = sum(float(row.get("value_gbp") or 0.0) for row in rows)
    cost = sum(float(row.get("known_cost_gbp") or 0.0) for row in rows)
    complete = all(row.get("complete") for row in rows)
    if value <= 0:
        return Resolved(None, None)
    if cost <= 0 and not complete:
        # Charges unknown, not zero: leave the simulation gross and say so in the caveats (#7834).
        return Resolved(None, None, ["The pension's fund charges are unknown, so no fees are deducted."])
    pct = round(cost / value * 100.0, 4)
    notes = (
        []
        if complete
        else [f"The {pct}% fee is a lower bound: some holdings have no known charge or some trades no fee data."]
    )
    return Resolved(pct, "all_in_cost", notes)


def pension_fee(
    owner: str,
    accounts_root: Path,
    transactions: Callable[[], Iterable[Any]],
    on: dt.date,
) -> Resolved:
    """The owner's DC pension all-in cost % from the current portfolio and the last 12 months' fees."""
    from backend.common.portfolio import build_owner_portfolio
    from backend.fund_upkeep.all_in_cost import compute_all_in_cost
    from backend.timeseries.cache import cache_only

    try:
        portfolio = build_owner_portfolio(owner, accounts_root)
    except FileNotFoundError as exc:
        logger.warning("No portfolio for the readiness fee estimate: %s", sanitise_log_value(exc))
        return Resolved(None, None)
    owned = [tx for tx in map(_as_mapping, transactions()) if str(tx.get("owner") or "").lower() == owner.lower()]
    with cache_only():
        all_in = compute_all_in_cost(portfolio, owned, today=on)
    return dc_fee_pct(all_in)


__all__ = ["Resolved", "dc_fee_pct", "pension_fee", "schedule_annual_gbp", "scheduled_contribution"]
