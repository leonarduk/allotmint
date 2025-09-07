"""Determine growth stage for holdings."""
from __future__ import annotations
from typing import Optional, Dict

StageInfo = Dict[str, str]

def get_growth_stage(
    days_held: Optional[int] = None,
    current_price: Optional[float] = None,
    target_price: Optional[float] = None,
) -> StageInfo:
    """Return a dictionary describing the growth stage of a holding."""
    if (
        target_price is not None
        and current_price is not None
        and current_price >= target_price
    ):
        return {
            "stage": "harvest",
            "icon": "🍾",
            "message": "Target met – consider selling.",
        }
    if days_held is not None and days_held >= 180:
        return {
            "stage": "harvest",
            "icon": "🍾",
            "message": "Long-term hold – review position.",
        }
    if days_held is not None and days_held >= 30:
        return {
            "stage": "growing",
            "icon": "🌿",
            "message": "Growing – monitor performance.",
        }
    return {
        "stage": "seed",
        "icon": "🌱",
        "message": "New position – give it time to grow.",
    }
