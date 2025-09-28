import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.common import compliance, data_loader
from backend.common.errors import handle_owner_not_found, raise_owner_not_found
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory

router = APIRouter(tags=["compliance"])
logger = logging.getLogger(__name__)


class KnownOwnerSet(set[str]):
    """Set of owners discovered for the active accounts root."""

    def __init__(self, iterable=(), *, active_root_has_entries: bool = False):
        super().__init__(iterable)
        self.active_root_has_entries = active_root_has_entries


def _known_owners(accounts_root) -> KnownOwnerSet:
    """Return a lower-cased set of known owners for the configured root."""

    owners = KnownOwnerSet()
    active_root_has_entries = False
    allow_demo_injection = False

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

    list_plots_failed = False
    try:
        entries = data_loader.list_plots(accounts_root)
    except Exception:
        entries = []
        list_plots_failed = True
    else:
        allow_demo_injection = True

    for entry in entries:
        owner = (entry.get("owner") or "").strip()
        if owner:
            owners.add(owner.lower())

    if owners:
        active_root_has_entries = True

    allow_demo_injection = allow_demo_injection and not list_plots_failed

    if owners:
        if allow_demo_injection:
            _ensure_demo_owner(owners)
        owners.active_root_has_entries = active_root_has_entries
        return owners

    if not list_plots_failed:
        owners.active_root_has_entries = active_root_has_entries
        return owners

    try:
        root_path = (
            Path(accounts_root)
            if accounts_root
            else data_loader.resolve_paths(None, None).accounts_root
        )
    except Exception:
        owners.active_root_has_entries = active_root_has_entries
        return owners

    if not root_path or not root_path.exists():
        owners.active_root_has_entries = active_root_has_entries
        return owners

    for entry in root_path.iterdir():
        if entry.is_dir():
            owners.add(entry.name.lower())

    if owners:
        active_root_has_entries = True
        if allow_demo_injection:
            _ensure_demo_owner(owners)

    owners.active_root_has_entries = active_root_has_entries
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
    discovered_for_active_root = getattr(
        owners, "active_root_has_entries", bool(owners)
    )
    owner_dir = resolve_owner_directory(accounts_root, owner_value)
    scaffold_missing = owner_dir is None

    if owner_dir:
        canonical_owner = owner_dir.name
        if discovered_for_active_root and canonical_owner.lower() not in owners:
            raise_owner_not_found()
        trade["owner"] = canonical_owner
    else:
        if discovered_for_active_root:
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
