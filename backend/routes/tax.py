from __future__ import annotations

import logging
from typing import Any, List

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from backend.auth import get_active_user
from backend.common import data_loader
from backend.common.core_optional import require_core
from backend.common.tax import harvest_losses
from backend.config import demo_identity
from backend.logging_setup import sanitise_log_value

try:
    from backend.common.allowances import current_tax_year, remaining_allowances
except ModuleNotFoundError:
    current_tax_year = None
    remaining_allowances = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tax", tags=["tax"])

ALLOWANCE_USAGE_UNAVAILABLE = "Allowance usage could not be derived from the transaction ledger"


class Position(BaseModel):
    ticker: str
    basis: float
    price: float


class HarvestRequest(BaseModel):
    positions: List[Position]
    threshold: float | None = None


@router.post("/harvest")
def harvest(req: HarvestRequest) -> dict:
    trades = harvest_losses([p.model_dump() for p in req.positions], req.threshold or 0.0)
    return {"trades": trades}


@router.get("/allowances")
async def allowances(request: Request, owner: str | None = Query(None)) -> dict:
    """Return remaining ISA and pension allowances for ``owner``.

    When auth is enabled and ``owner`` is not provided, the authenticated user
    is used.  When auth is disabled, the configured demo account is used.
    """
    require_core(current_tax_year, "Tax allowances")

    active_user = await get_active_user(request)
    if owner is None:
        if active_user is not None:
            owner = active_user
        else:
            aliases = data_loader.demo_identity_aliases()
            preferred = next((a for a in aliases if a.lower() == "demo"), None)
            owner = preferred or (aliases[0] if aliases else demo_identity())
    tax_year = current_tax_year()
    data = _derived_allowances(owner, tax_year)
    return {"owner": owner, "tax_year": tax_year, "allowances": data}


def _derived_allowances(owner: str, tax_year: Any) -> Any:
    """``remaining_allowances`` for ``owner``, or a 503 when the ledger can't be read.

    Usage is derived from the transaction ledger, which raises rather than
    reporting zero used when it is unreadable or malformed. Never answer 200
    with ``used: 0`` here: that shows the full allowance as headroom (#10796).
    """
    try:
        return remaining_allowances(owner, tax_year)
    except (OSError, ValueError, RuntimeError) as exc:
        logger.exception(
            "Allowance usage unavailable for owner %s, tax year %s",
            sanitise_log_value(owner),
            sanitise_log_value(tax_year),
        )
        raise HTTPException(status_code=503, detail=ALLOWANCE_USAGE_UNAVAILABLE) from exc
