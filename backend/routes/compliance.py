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
    discovery_successful = False

    specified_root: Path | None
    try:
        specified_root = Path(accounts_root) if accounts_root is not None else None
    except (TypeError, ValueError):
        specified_root = None

    def _ensure_demo_owner(owner_set: set[str]) -> None:
        """Ensure the bundled demo owner remains discoverable."""

        if not owner_set or "demo" in owner_set:
            return

        try:
            fallback_root = data_loader.resolve_paths(None, None).accounts_root
        except Exception:
            return

        try:
            demo_dir = fallback_root / "demo"
        except TypeError:
            return

        try:
            if demo_dir.exists() and demo_dir.is_dir():
                owner_set.add("demo")
        except Exception:
            return

    try:
        entries = data_loader.list_plots(accounts_root)
    except Exception:
        entries = []
    else:
        discovery_successful = True

    if specified_root is not None and not specified_root.exists():
        discovery_successful = False
        entries = []

    for entry in entries:
        owner = (entry.get("owner") or "").strip()
        if owner:
            owners.add(owner.lower())

    if owners:
        if discovery_successful:
            _ensure_demo_owner(owners)
        return owners

    try:
        root_path = (
            Path(accounts_root)
            if accounts_root
            else data_loader.resolve_paths(None, None).accounts_root
        )
    except Exception:
        if discovery_successful:
            _ensure_demo_owner(owners)
        return owners

    if not root_path or not root_path.exists():
        if discovery_successful:
            _ensure_demo_owner(owners)
        return owners

    discovery_successful = True

    for entry in root_path.iterdir():
        if entry.is_dir():
            owners.add(entry.name.lower())

    if discovery_successful:
        _ensure_demo_owner(owners)
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
    accounts_root = resolve_accounts_root(request, allow_missing=True)
    raw_owner = trade.get("owner")
    owner_value = " ".join(str(raw_owner or "").split()).strip()
    if not owner_value:
        raise_owner_not_found()

    owners = _known_owners(accounts_root)
    owner_dir = resolve_owner_directory(accounts_root, owner_value)
    scaffold_missing = owner_dir is None

    if owner_dir:
        canonical_owner = owner_dir.name
        if owners and canonical_owner.lower() not in owners:
            raise_owner_not_found()
        trade["owner"] = canonical_owner
    else:
        if owners:
            raise_owner_not_found()
        trade["owner"] = owner_value
    try:
        result = compliance.check_trade(
            trade,
            accounts_root,
            scaffold_missing=scaffold_missing,
        )
    except FileNotFoundError:
        raise_owner_not_found()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if scaffold_missing:
        try:
            compliance.ensure_owner_scaffold(trade["owner"], accounts_root)
        except Exception:
            logger.warning("failed to scaffold compliance data for %s", trade.get("owner"))

    return result
