"""Tranche split and draft order list for one cash deployment tranche (#10480).

The split is exactly :func:`backend.common.sleeve_plan.sleeve_new_cash` (the
``/rebalance/{owner}/new-cash`` computation, core sleeve), which delegates to
:func:`backend.common.rebalance_plan.suggest_new_cash`; nothing here re-derives
it. Each bought class is then paired with the first vehicle the owner's plan
lists for it, and nothing else: a class with no plan vehicle gets no
instrument. Indicative units use the latest cached close in GBP, which
:func:`backend.common.holding_utils.load_latest_prices` already normalises
from pence (GBX) for ``.L`` lines.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Mapping, Optional

from backend.common.allocation_policy import AllocationPolicy, parse_policy
from backend.common.investment_plan import _POLICY_TO_PLAN_CLASS, InvestmentPlan, rebalance_weights
from backend.common.sleeve_plan import sleeve_new_cash
from backend.common.sleeves import CORE_ID, SleeveSetup

#: Shown with every order list: the owner's own plan, placed by the owner.
ORDER_LIST_LABEL = "Draft order list per your plan. Place these yourself at your broker; nothing is traded for you."

PriceLookup = Callable[[list[str]], Mapping[str, float]]


def target_policy(source: str, saved: AllocationPolicy, plan: Optional[InvestmentPlan]) -> AllocationPolicy:
    """The targets a tranche invests towards: the plan's (in policy vocabulary) or the saved rebalance policy."""
    if source == "policy":
        if not saved.targets:
            raise ValueError("Set target allocations before planning a tranche")
        return saved
    if plan is None:
        raise ValueError("This schedule invests towards your investment plan, but no plan is saved")
    targets = parse_policy({"targets": rebalance_weights(plan)}).targets
    return AllocationPolicy(targets=targets, tolerance_pct=saved.tolerance_pct)


def plan_vehicle(plan: Optional[InvestmentPlan], policy_key: str) -> dict[str, Optional[str]]:
    """The plan's first vehicle for a policy class key, or blanks when the plan names none."""
    if plan is None:
        return {"ticker": None, "note": None}
    vehicles = plan.vehicles.get(_POLICY_TO_PLAN_CLASS.get(policy_key, policy_key)) or []
    if not vehicles:
        return {"ticker": None, "note": None}
    first = vehicles[0]
    ticker = first.ticker.strip().upper() if first.ticker else None
    return {"ticker": ticker, "note": first.note}


def indicative_units(amount_gbp: float, price_gbp: Optional[float]) -> Optional[float]:
    """Units ``amount_gbp`` buys at ``price_gbp``, rounded down to 4 dp; ``None`` without a usable price."""
    if price_gbp is None or not math.isfinite(price_gbp) or price_gbp <= 0:
        return None
    return math.floor(amount_gbp / price_gbp * 10_000) / 10_000


def _order(trade: Mapping[str, Any], plan: Optional[InvestmentPlan], prices: Mapping[str, float]) -> dict[str, Any]:
    vehicle = plan_vehicle(plan, trade["asset_class"])
    price = prices.get(vehicle["ticker"]) if vehicle["ticker"] else None
    amount_gbp = float(trade["amount"])
    return {
        "asset_class": trade["asset_class"],
        "ticker": vehicle["ticker"],
        "vehicle_note": vehicle["note"],
        "amount_minor": round(amount_gbp * 100),
        "price_gbp": round(price, 4) if price is not None else None,
        "indicative_units": indicative_units(amount_gbp, price),
    }


def default_prices(tickers: list[str]) -> Mapping[str, float]:
    from backend.common.holding_utils import load_latest_prices

    return load_latest_prices(tickers)


def build_tranche(
    portfolio: Mapping[str, Any],
    policy: AllocationPolicy,
    setup: SleeveSetup,
    plan: Optional[InvestmentPlan],
    account_id: str,
    amount_minor: int,
    prices: PriceLookup = default_prices,
) -> dict[str, Any]:
    """Split one tranche with ``sleeve_new_cash`` and draft its order list from the plan's vehicles."""
    split = sleeve_new_cash(portfolio, policy, setup, CORE_ID, amount_minor / 100.0, account_id)
    tickers = sorted({t for t in (plan_vehicle(plan, tr["asset_class"])["ticker"] for tr in split["trades"]) if t})
    price_map = {key.upper(): value for key, value in (prices(tickers) if tickers else {}).items()}
    return {
        "amount_minor": amount_minor,
        "label": ORDER_LIST_LABEL,
        "split": split,
        "orders": [_order(trade, plan, price_map) for trade in split["trades"]],
        "keep_as_cash_minor": round(float(split["keep_as_cash"]) * 100),
    }
