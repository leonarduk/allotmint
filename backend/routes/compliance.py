from fastapi import APIRouter, Request, HTTPException

from backend.common import compliance
from backend.common.errors import handle_owner_not_found, raise_owner_not_found

router = APIRouter(tags=["compliance"])


@router.get("/compliance/{owner}")
@handle_owner_not_found
async def compliance_for_owner(owner: str, request: Request):
    """Return compliance warnings and status for an owner."""
    try:
        # ``check_owner`` now returns additional fields such as
        # ``hold_countdowns`` and ``trades_remaining`` which are
        # forwarded directly to the client.
        return compliance.check_owner(owner, request.app.state.accounts_root)
    except FileNotFoundError:
        raise_owner_not_found()


@router.post("/compliance/validate")
@handle_owner_not_found
async def validate_trade(request: Request):
    """Validate a proposed trade for compliance issues.

    The returned payload mirrors :func:`compliance_for_owner` and
    includes warning messages along with hold-period countdowns and
    the remaining trade quota for the current month.
    """
    trade = await request.json()
    if "owner" not in trade:
        raise HTTPException(status_code=422, detail="owner is required")
    try:
        return compliance.check_trade(trade, request.app.state.accounts_root)
    except FileNotFoundError:
        raise_owner_not_found()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
