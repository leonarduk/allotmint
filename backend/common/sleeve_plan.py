"""Per-sleeve drift and trades for the strategy page (#9813).

Splits an owner portfolio by the sleeve tags in
:class:`~backend.common.sleeves.SleeveSetup` and runs
:func:`~backend.common.rebalance_plan.build_plan` on each part against that
sleeve's own targets, so speculative holdings never count towards the core's
drift. The response keeps the single-plan shape at the top level (the core
sleeve), adding ``portfolio_total`` and a ``sleeves`` list with each sleeve's
size drift and, for non-core sleeves, its own plan.

With no sleeves configured the result is exactly :func:`build_plan` on the
whole portfolio.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from backend.common.allocation_policy import AllocationPolicy
from backend.common.rebalance_plan import bucket_holdings, build_plan, split_classes, suggest_new_cash
from backend.common.sleeves import CORE_ID, CORE_NAME, SleeveSetup


def split_portfolio(portfolio: Mapping[str, Any], setup: SleeveSetup) -> dict[str, dict[str, Any]]:
    """One portfolio per sleeve id (core included), each keeping every account and only its holdings."""
    ids = [CORE_ID, *(s.id for s in setup.sleeves)]
    parts: dict[str, dict[str, Any]] = {i: {**portfolio, "accounts": []} for i in ids}
    for account in portfolio.get("accounts") or []:
        by_sleeve: dict[str, list[Any]] = {i: [] for i in ids}
        for holding in account.get("holdings") or []:
            by_sleeve[setup.sleeve_of(str(holding.get("ticker") or ""))].append(holding)
        for sleeve_id in ids:
            parts[sleeve_id]["accounts"].append({**account, "holdings": by_sleeve[sleeve_id]})
    return parts


def sleeve_policy(setup: SleeveSetup, sleeve_id: str, policy: AllocationPolicy) -> AllocationPolicy:
    """The targets a sleeve is measured against; every sleeve shares the core's drift tolerance."""
    if sleeve_id == CORE_ID:
        return policy
    sleeve = next((s for s in setup.sleeves if s.id == sleeve_id), None)
    if sleeve is None:
        raise ValueError(f"Unknown sleeve {sleeve_id!r}")
    return AllocationPolicy(targets=dict(sleeve.targets), tolerance_pct=policy.tolerance_pct)


#: A sleeve is out of band once its size drifts by the drift tolerance or by
#: this share of its own target, whichever is smaller (the "5/25" rule). A
#: flat 5pp band would let a 10% sleeve reach 15% unnoticed.
SIZE_RELATIVE_BAND = 0.25


def size_band(target_pct: float, tolerance_pct: float) -> float:
    """Allowed size drift in pp for a sleeve with ``target_pct`` of the portfolio."""
    return min(tolerance_pct, target_pct * SIZE_RELATIVE_BAND)


def _pct(value: float, total: float) -> float:
    return value / total * 100.0 if total > 0 else 0.0


def _size_row(
    sleeve_id: str,
    name: str,
    target: float,
    value: float,
    total: float,
    tolerance: float,
) -> dict[str, Any]:
    current = _pct(value, total)
    drift = current - target
    band = size_band(target, tolerance)
    return {
        "id": sleeve_id,
        "name": name,
        "size_target_pct": round(target, 2),
        "current_value": round(value, 2),
        "size_current_pct": round(current, 2),
        "size_drift_pct": round(drift, 2),
        "size_band_pct": round(band, 2),
        "in_band": abs(drift) <= band if total > 0 else None,
    }


def _size_notes(rows: list[dict[str, Any]]) -> list[str]:
    return [
        f"The {row['name']} sleeve is {row['size_current_pct']:.2f}% of the portfolio against a "
        f"{row['size_target_pct']:.2f}% target (more than {row['size_band_pct']:g}pp out); move money between sleeves "
        "or change the sleeve size."
        for row in rows
        if row["in_band"] is False
    ]


def build_sleeved_plan(
    portfolio: Mapping[str, Any],
    policy: AllocationPolicy,
    setup: SleeveSetup,
    core_strategy: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """The rebalance plan, split by sleeve when the owner has any."""
    if not setup.sleeves:
        return build_plan(portfolio, policy)
    parts = split_portfolio(portfolio, setup)
    core = build_plan(parts[CORE_ID], policy)
    plans = {s.id: build_plan(parts[s.id], sleeve_policy(setup, s.id, policy)) for s in setup.sleeves}
    total = core["total_value"] + sum(p["total_value"] for p in plans.values())
    tolerance = policy.tolerance_pct
    core_row = _size_row(CORE_ID, CORE_NAME, setup.core_size_pct, core["total_value"], total, tolerance)
    core_row["strategy"] = dict(core_strategy) if core_strategy else None
    rows = [core_row]
    for sleeve in setup.sleeves:
        row = _size_row(sleeve.id, sleeve.name, sleeve.size_pct, plans[sleeve.id]["total_value"], total, tolerance)
        row.update(strategy=sleeve.strategy, plan=plans[sleeve.id])
        rows.append(row)
    core["portfolio_total"] = round(total, 2)
    core["sleeves"] = rows
    core["notes"] = [
        f"Drift and trades for the Core sleeve cover £{core['total_value']:,.2f} of the £{total:,.2f} portfolio; "
        "other sleeves are planned separately.",
        *_size_notes(rows),
        *core["notes"],
    ]
    return core


def sleeve_new_cash(
    portfolio: Mapping[str, Any],
    policy: AllocationPolicy,
    setup: SleeveSetup,
    sleeve_id: str,
    amount: float,
    account_id: str,
) -> dict[str, Any]:
    """Buy-only allocation of new cash paid into one account, aimed at one sleeve's targets."""
    target_policy = sleeve_policy(setup, sleeve_id, policy)
    part = split_portfolio(portfolio, setup)[sleeve_id] if setup.sleeves else portfolio
    holdings = bucket_holdings(part, split_classes(target_policy))
    return suggest_new_cash(holdings, target_policy, amount, account_id)
