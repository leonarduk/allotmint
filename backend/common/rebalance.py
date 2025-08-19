from __future__ import annotations

"""Helpers for portfolio rebalancing.

This module provides a small utility that compares the current market value
allocation of a portfolio with a target weight distribution and suggests
trades required to align the two.  The implementation intentionally keeps the
inputs simple to make the function easy to reuse in tests and routers.
"""

from typing import Dict, List


def suggest_trades(actual: Dict[str, float], target: Dict[str, float]) -> List[dict]:
    """Return suggested trades to move ``actual`` weights towards ``target``.

    Parameters
    ----------
    actual:
        Mapping of ticker symbol to current market value.
    target:
        Mapping of ticker symbol to desired portfolio weight expressed as a
        fraction (e.g. ``0.25`` for 25%).  Missing tickers imply a target of
        zero.

    Returns
    -------
    list of dict
        Each entry has ``ticker`` (str), ``action`` ("buy" or "sell") and
        ``amount`` (float, absolute currency amount to trade).
    """

    total_value = sum(actual.values())
    suggestions: List[dict] = []
    tickers = set(actual) | set(target)

    for t in sorted(tickers):
        current_val = float(actual.get(t, 0.0))
        target_val = float(target.get(t, 0.0)) * total_value
        diff = target_val - current_val
        # Ignore negligible differences to avoid suggesting dust trades
        if abs(diff) < 1e-6:
            continue
        suggestions.append(
            {
                "ticker": t,
                "action": "buy" if diff > 0 else "sell",
                "amount": round(abs(diff), 2),
            }
        )

    return suggestions
