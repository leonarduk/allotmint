import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from backend.common import compliance, data_loader
from backend.common.errors import handle_owner_not_found, raise_owner_not_found

router = APIRouter(tags=["compliance"])
logger = logging.getLogger(__name__)


def _resolve_accounts_root(accounts_root: Optional[object]) -> Optional[Path]:
    """Normalise ``accounts_root`` to a :class:`Path` when possible."""

    if accounts_root is None:
        return None
    try:
        return Path(accounts_root)
    except TypeError:
        return Path(str(accounts_root))


def _known_owners(accounts_root) -> set[str]:
    """Return a lower-cased set of known owners for the configured root."""

    owners: set[str] = set()
    root_hint = _resolve_accounts_root(accounts_root)
    try:
        root_path = root_hint or data_loader.resolve_paths(None, None).accounts_root
    except Exception:
        root_path = None
    else:
        if not root_path.exists():
            root_path = None

    list_root = root_hint
    for entry in data_loader.list_plots(list_root):
        owner = (entry.get("owner") or "").strip()
        if not owner:
            continue
        if root_path:
            owner_dir = root_path / owner
            if not owner_dir.exists():
                try:
                    owner_dir = next(p for p in root_path.iterdir() if p.is_dir() and p.name.lower() == owner.lower())
                except StopIteration:
                    owner_dir = None
            if not owner_dir or not owner_dir.is_dir():
                continue
        owners.add(owner.lower())
    return owners


@router.get("/compliance/{owner}")
@handle_owner_not_found
async def compliance_for_owner(owner: str, request: Request):
    """Return compliance warnings and status for an owner."""
    accounts_root = request.app.state.accounts_root
    owners = _known_owners(accounts_root)
    if owner.lower() not in owners:
        raise_owner_not_found()
    try:
        # ``check_owner`` now returns additional fields such as
        # ``hold_countdowns`` and ``trades_remaining`` which are
        # forwarded directly to the client.
        return compliance.check_owner(owner, accounts_root)
    except FileNotFoundError as exc:
        logger.warning("accounts for %s not found: %s", owner, exc)
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
    accounts_root = request.app.state.accounts_root
    owners = _known_owners(accounts_root)
    if trade.get("owner", "").lower() not in owners:
        raise_owner_not_found()
    try:
        return compliance.check_trade(trade, accounts_root)
    except FileNotFoundError:
        raise_owner_not_found()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
