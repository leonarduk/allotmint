import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.common import compliance, data_loader
from backend.common.errors import handle_owner_not_found, raise_owner_not_found
from backend.routes._accounts import resolve_accounts_root, resolve_owner_directory

router = APIRouter(tags=["compliance"])
logger = logging.getLogger(__name__)


def _known_owners(accounts_root) -> tuple[set[str], bool]:
    """Return a set of known owners and whether discovery succeeded.

    The second return value indicates whether discovery produced a non-empty
    result for the active ``accounts_root``. Callers can use this to avoid
    blocking requests when discovery failed outright (for example, when the
    configured root no longer exists).
    """

    owners: set[str] = set()

    try:
        active_root = Path(accounts_root) if accounts_root else data_loader.resolve_paths(None, None).accounts_root
    except Exception:
        active_root = None

    active_root_exists = False
    if active_root is not None:
        try:
            active_root_exists = active_root.exists()
        except Exception:
            active_root_exists = False

    discovery_failed = False

    def _ensure_demo_owner(owner_set: set[str], *, allow_fallback: bool) -> None:
        """Ensure the bundled demo owner remains discoverable."""

        if not allow_fallback or not owner_set or "demo" in owner_set:
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
        discovery_failed = True

    has_discovered_owner = False

    for entry in entries:
        owner = (entry.get("owner") or "").strip()
        if owner:
            owners.add(owner.lower())
            if active_root_exists:
                has_discovered_owner = True

    allow_demo = not discovery_failed and active_root_exists
    _ensure_demo_owner(owners, allow_fallback=allow_demo)

    if has_discovered_owner:
        return owners, True

    if not active_root_exists:
        return owners, False

    try:
        for entry in active_root.iterdir():
            if entry.is_dir():
                owners.add(entry.name.lower())
    except Exception:
        return owners, False

    _ensure_demo_owner(owners, allow_fallback=allow_demo)
    return owners, False


@router.get("/compliance/{owner}")
@handle_owner_not_found
async def compliance_for_owner(owner: str, request: Request):
    """Return compliance warnings and status for an owner."""
    accounts_root = resolve_accounts_root(request)
    owner_dir = resolve_owner_directory(accounts_root, owner)
    if not owner_dir:
        raise_owner_not_found()
    owner = owner_dir.name
    owners, _ = _known_owners(accounts_root)
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

    owners, discovery_success = _known_owners(accounts_root)
    owner_dir = resolve_owner_directory(accounts_root, owner_value)
    scaffold_missing = owner_dir is None

    if owner_dir:
        canonical_owner = owner_dir.name
        if discovery_success and owners and canonical_owner.lower() not in owners:
            raise_owner_not_found()
        trade["owner"] = canonical_owner
    else:
        if discovery_success and owners:
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
