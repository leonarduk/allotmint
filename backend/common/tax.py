from __future__ import annotations

from typing import Dict, List


def harvest_losses(positions: List[Dict[str, float]], threshold: float = 0.0) -> List[Dict[str, float]]:
    """Return positions that qualify for tax loss harvesting.

    Parameters
    ----------
    positions: list of dicts with ``ticker``, ``basis`` and ``price`` fields.
    threshold: minimum fractional loss required to trigger a harvest.
    """
    results: List[Dict[str, float]] = []
    for pos in positions:
        try:
            basis = float(pos.get("basis", 0.0))
            price = float(pos.get("price", 0.0))
        except (TypeError, ValueError):
            continue
        if basis <= 0:
            continue
        loss = basis - price
        if loss / basis >= threshold:
            results.append({"ticker": pos.get("ticker"), "loss": round(loss, 2)})
    return results


__all__ = ["harvest_losses"]
