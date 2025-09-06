"""Utility helpers for simple price-shock scenarios."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable

from backend.common.constants import (
    COST_BASIS_GBP,
    EFFECTIVE_COST_BASIS_GBP,
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
                cost = float(h.get(EFFECTIVE_COST_BASIS_GBP) or h.get(COST_BASIS_GBP) or 0.0)
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


def apply_historical_event(
    portfolio: Dict[str, Any],
    event_id: str | None = None,
    date: str | None = None,
    horizons: Iterable[int] | None = None,
) -> Dict[int, Dict[str, Any]]:
    """Return shocked portfolios for each horizon of a historical event.

    This helper currently applies a simple uniform scaling to the portfolio's
    account values for each requested horizon. The scaling factor is derived
    from the horizon length (e.g. a horizon of ``1`` applies a 1% drop). The
    original ``portfolio`` is not modified.
    """

    horizons = list(horizons or [1])
    shocked: Dict[int, Dict[str, Any]] = {}
    for horizon in horizons:
        factor = max(0.0, 1 - horizon / 100.0)
        pf_copy = deepcopy(portfolio)
        for acct in pf_copy.get("accounts", []):
            val = float(acct.get("value_estimate_gbp") or 0.0) * factor
            acct["value_estimate_gbp"] = round(val, 2)
        pf_copy["total_value_estimate_gbp"] = round(
            sum(a.get("value_estimate_gbp") or 0.0 for a in pf_copy.get("accounts", [])),
            2,
        )
        shocked[horizon] = pf_copy
    return shocked
