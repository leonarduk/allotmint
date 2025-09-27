import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.common import compliance, data_loader
from backend.common.errors import handle_owner_not_found, raise_owner_not_found
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory

router = APIRouter(tags=["compliance"])
logger = logging.getLogger(__name__)


def _known_owners(accounts_root) -> set[str]:
    """Return a lower-cased set of known owners for the configured root."""

    owners: set[str] = set()
    try:
        entries = data_loader.list_plots(accounts_root)
    except Exception:
        entries = []

    for entry in entries:
        owner = (entry.get("owner") or "").strip()
        if owner:
            owners.add(owner.lower())

    try:
        root_path = (
            Path(accounts_root)
            if accounts_root
            else data_loader.resolve_paths(None, None).accounts_root
        )
    except Exception:
        root_path = None

    if root_path and root_path.exists():
        for entry in root_path.iterdir():
            if entry.is_dir():
                owners.add(entry.name.lower())

    return owners


@router.get("/compliance/{owner}")
@handle_owner_not_found
async def compliance_for_owner(owner: str, request: Request):
    """Return compliance warnings and status for an owner."""
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if not owner_dir:
        raise_owner_not_found()
    owner = owner_dir.name
    owners = _known_owners(accounts_root)
    if owners and owner.lower() not in owners:
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
    accounts_root = resolve_accounts_root(request)
    owner_value = (trade.get("owner") or "").strip()
    if not owner_value:
        raise_owner_not_found()

    owners = _known_owners(accounts_root)
    owner_dir = resolve_owner_directory(accounts_root, owner_value)

    if owner_dir:
        canonical_owner = owner_dir.name
        if owners and canonical_owner.lower() not in owners:
            raise_owner_not_found()
        trade["owner"] = canonical_owner
    else:
        if owners:
            raise_owner_not_found()
        owner_dir = compliance.ensure_owner_scaffold(owner_value, accounts_root)
        accounts_root = owner_dir.parent
        request.app.state.accounts_root = accounts_root
        trade["owner"] = owner_dir.name
    try:
        return compliance.check_trade(trade, accounts_root)
    except FileNotFoundError:
        raise_owner_not_found()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
