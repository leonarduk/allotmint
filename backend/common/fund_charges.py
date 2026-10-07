"""Fund ongoing charges (OCF/TER) read from instrument metadata (#7834).

The charge is entered by the user in the instrument metadata catalogue as
``ongoing_charge_pct`` (a percentage per year, e.g. ``0.22`` for 0.22%), taken
from the fund's own KIID/factsheet. No third-party OCF feed is used, so there
is no data-licensing dependency.

A missing or unusable value is ``None`` ("unknown") -- never ``0.0`` -- so a
holding with no fee data cannot understate the portfolio's total cost.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional

ONGOING_CHARGE_KEY = "ongoing_charge_pct"

# No real fund charges anywhere near this; a larger value is a data-entry slip
# (e.g. 22 typed for 0.22%) and is treated as unknown rather than trusted.
_MAX_PLAUSIBLE_CHARGE_PCT = 10.0


def ongoing_charge_pct(meta: Optional[Mapping[str, Any]]) -> Optional[float]:
    """Return the stored annual ongoing charge as a percentage, or ``None``."""

    if not meta:
        return None
    value = meta.get(ONGOING_CHARGE_KEY)
    if value is None or isinstance(value, bool):
        return None
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(pct) or pct < 0 or pct > _MAX_PLAUSIBLE_CHARGE_PCT:
        return None
    return pct
