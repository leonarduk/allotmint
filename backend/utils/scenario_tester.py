"""Utility helpers for simple price-shock scenarios."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from backend.common.constants import (
    EFFECTIVE_COST_BASIS_GBP,
    COST_BASIS_GBP,
)
from backend.common.prices import get_price_gbp


def apply_price_shock(portfolio: Dict[str, Any], ticker: str, pct_change: float) -> Dict[str, Any]:
    """Return a new portfolio with ``ticker`` shocked by ``pct_change`` percent.

    ``pct_change`` is interpreted as a percentage (e.g. ``5`` for +5%).
    The function recalculates affected holding metrics, account totals and the
    overall portfolio total.  The original ``portfolio`` is not modified.
    """

    shocked = deepcopy(portfolio)
    target = ticker.upper()
    factor = 1 + pct_change / 100.0

    for acct in shocked.get("accounts", []):
        total = 0.0
        for h in acct.get("holdings", []):
            tkr = (h.get("ticker") or "").upper()
            units = float(h.get("units") or 0.0)
            if tkr == target:
                price = float(h.get("current_price_gbp") or h.get("price") or 0.0)
                if price == 0:
                    cached = get_price_gbp(tkr)
                    price = float(cached or 0.0)
                new_price = price * factor
                cost = float(
                    h.get(EFFECTIVE_COST_BASIS_GBP)
                    or h.get(COST_BASIS_GBP)
                    or 0.0
                )
                mv = units * new_price
                gain = mv - cost
                h["price"] = h["current_price_gbp"] = round(new_price, 4)
                h["market_value_gbp"] = round(mv, 2)
                h["gain_gbp"] = round(gain, 2)
                h["unrealised_gain_gbp"] = h["unrealized_gain_gbp"] = round(gain, 2)
                h["gain_pct"] = round((gain / cost * 100.0), 2) if cost else None
                h["day_change_gbp"] = round((new_price - price) * units, 2)
            total += float(h.get("market_value_gbp") or 0.0)
        acct["value_estimate_gbp"] = round(total, 2)

    shocked["total_value_estimate_gbp"] = round(
        sum(a.get("value_estimate_gbp") or 0.0 for a in shocked.get("accounts", [])),
        2,
    )
    return shocked
