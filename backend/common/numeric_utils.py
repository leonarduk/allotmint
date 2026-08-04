"""Small numeric helpers shared across pricing/holdings modules."""

from __future__ import annotations

import math
from typing import Any, Optional


def clean_price(value: Any) -> Optional[float]:
    """Coerce ``value`` to ``float``, treating ``None``/NaN as "no price".

    Centralises the "fetch a price, guard against NaN" pattern repeated
    across the pricing/holdings modules (see issue #5210).
    """

    if value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(price) else price
