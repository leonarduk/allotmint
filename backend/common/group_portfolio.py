from __future__ import annotations

"""
Group portfolio aggregation for AllotMint.

Group membership is **calculated live** every request (no cache).  To debug the
age classification logic you only need to set an env‑var:

```
set ALLOTMINT_GROUP_LOG_LEVEL=DEBUG   # Windows PowerShell / cmd
export ALLOTMINT_GROUP_LOG_LEVEL=DEBUG  # macOS / Linux / WSL
```

The module now adds its **own handler** to ``allotmint.groups`` and sets
``propagate = False`` so the messages go straight to stdout even when the root
handler (installed by Uvicorn) is pinned to INFO.  Example output:

```
2025-07-24 14:10:43 [allotmint.groups] DEBUG: alex  -> age 12 (child)
2025-07-24 14:10:43 [allotmint.groups] DEBUG: steve -> age 46 (adult)
```
"""

import logging
import os
import sys
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from backend.common.data_loader import list_plots, load_person_meta
from backend.common.portfolio import build_owner_portfolio

__all__ = [
    "list_groups",
    "build_group_portfolio",
]

# ---------------------------------------------------------------------------
# Logger setup
# ---------------------------------------------------------------------------
logger = logging.getLogger("allotmint.groups")
logger.propagate = False  # bypass root logger’s level (usually INFO)

if not logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setLevel(logging.DEBUG)
    _h.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    )
    logger.addHandler(_h)

# honour optional env‑var override
_env_level = os.getenv("ALLOTMINT_GROUP_LOG_LEVEL")
if _env_level:
    logger.setLevel(_env_level.upper())
else:
    logger.setLevel(logging.DEBUG)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _as_decimal(value: Any) -> Decimal:
    """Convert *anything numeric* into :class:`~decimal.Decimal`."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _calc_age(meta: Dict[str, Any]) -> int:
    """Return integer age; default 18 when missing/invalid."""
    # explicit age
    try:
        age_raw = meta.get("age")
        if age_raw is not None:
            age_int = int(age_raw)
            if age_int >= 0:
                return age_int
    except Exception:
        pass

    # derive from dob
    dob_txt = (meta.get("dob") or meta.get("date_of_birth") or "").strip()
    if dob_txt:
        try:
            dob = date.fromisoformat(dob_txt)
            today = date.today()
            age_int = today.year - dob.year - (
                (today.month, today.day) < (dob.month, dob.day)
            )
            if age_int >= 0:
                return age_int
        except Exception:
            pass

    return 18  # default adult

# ---------------------------------------------------------------------------
# Dynamic group discovery
# ---------------------------------------------------------------------------

def _group_defs() -> Dict[str, List[str]]:
    plots = list_plots()  # [{"owner": "alex", "accounts": [...]}]
    owners = [p["owner"] for p in plots]

    adults: List[str] = []
    children: List[str] = []

    for owner in owners:
        age = _calc_age(load_person_meta(owner))
        bucket = "adult" if age >= 18 else "child"
        logger.debug("%s -> age %s (%s)", owner, age, bucket)
        (adults if age >= 18 else children).append(owner)

    return {
        "all": owners,
        "adults": adults,
        "children": children,
    }

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_groups() -> List[Dict[str, Any]]:
    defs = _group_defs()
    return [{"group": slug, "members": members} for slug, members in defs.items()]


def build_group_portfolio(group: str, env: Optional[str] = None) -> Dict[str, Any]:
    slug = group.lower()
    defs = _group_defs()
    if slug not in defs:
        raise KeyError(f"Unknown group '{group}'")

    members = defs[slug]
    today_iso = date.today().isoformat()

    group_total = Decimal("0")
    acct_subtotals: Dict[str, Decimal] = {}
    members_summary: List[Dict[str, Any]] = []

    for owner in members:
        p = build_owner_portfolio(owner, env=env)

        owner_total = _as_decimal(p["total_value_estimate_gbp"])
        group_total += owner_total

        members_summary.append({
            "owner": owner,
            "total_value_estimate_gbp": float(owner_total),
            "trades_this_month": int(p.get("trades_this_month", 0)),
            "trades_remaining": int(p.get("trades_remaining", 0)),
        })

        for acct in p["accounts"]:
            acct_type = str(acct.get("account_type", "UNKNOWN")).upper()
            acct_value = _as_decimal(acct["value_estimate_gbp"])
            acct_subtotals[acct_type] = acct_subtotals.get(acct_type, Decimal("0")) + acct_value

    return {
        "group": slug,
        "as_of":  today_iso,
        "members": members,
        "total_value_estimate_gbp": float(group_total),
        "members_summary": members_summary,
        "subtotals_by_account_type": {k: float(v) for k, v in acct_subtotals.items()},
    }
