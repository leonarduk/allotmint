"""Owner directory scaffolding and transaction loading.

Extracted from ``backend.common.compliance`` so the compliance *rule engine*
(``check_owner``, ``check_trade``, ``evaluate_trades``) can be split into a
private package later without dragging this generic, publicly-depended-on
account/transaction plumbing along with it. ``portfolio_utils``,
``metrics``, and ``signup_provision`` all depend on ``load_transactions``/
``ensure_owner_scaffold`` directly, independent of the compliance rules.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.common.data_loader import resolve_paths
from backend.common.path_utils import safe_join
from backend.config import config

logger = logging.getLogger(__name__)


def _default_settings_payload() -> Dict[str, Any]:
    """Build default settings for newly created owners."""

    payload: Dict[str, Any] = {}
    if config.hold_days_min is not None:
        payload["hold_days_min"] = config.hold_days_min
    else:
        payload["hold_days_min"] = 0

    if config.max_trades_per_month is not None:
        payload["max_trades_per_month"] = config.max_trades_per_month
    else:
        payload["max_trades_per_month"] = 0

    if config.approval_exempt_types:
        payload["approval_exempt_types"] = config.approval_exempt_types
    else:
        payload["approval_exempt_types"] = []

    if config.approval_exempt_tickers:
        payload["approval_exempt_tickers"] = config.approval_exempt_tickers
    else:
        payload["approval_exempt_tickers"] = []

    return payload


def _ensure_owner_scaffold(owner: str, owner_dir: Path) -> None:
    """Create the default directory and files for ``owner`` if absent."""

    owner_dir.mkdir(parents=True, exist_ok=True)

    defaults: Dict[str, Dict[str, Any]] = {
        "settings.json": _default_settings_payload(),
        "approvals.json": {"approvals": []},
        "person.json": {
            "dob": "",
            "email": "",
            "full_name": "",
            "owner": owner,
            "holdings": [],
            "viewers": [],
        },
        f"{owner}_transactions.json": {
            "account_type": "brokerage",
            "transactions": [],
        },
    }

    for filename, payload in defaults.items():
        try:
            path = safe_join(owner_dir, filename)
        except ValueError:
            logger.warning("skipping invalid scaffold filename: path traversal detected")
            continue
        if path.exists():
            continue
        try:
            path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        except OSError:
            logger.warning("failed to create default scaffold file")


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val).date()
    except Exception:
        return None


def ensure_owner_scaffold(owner: str, accounts_root: Optional[Path] = None) -> Path:
    """Explicit account-provisioning path used by the admin signup-approval flow.

    Called from :mod:`backend.common.signup_provision` when an admin approves a
    pending signup request.  Unlike
    :meth:`~backend.common.accounts_store.AccountsStore.ensure_owner`, this
    path runs *before* any user write and also records the owner's email in
    ``person.json`` so :func:`backend.auth._allowed_emails` admits them at
    login.  Idempotent: re-provisioning the same owner is a no-op.

    Returns the resolved owner directory after ensuring the default files are
    present.
    """
    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = Path(accounts_root) if accounts_root else paths.accounts_root
    try:
        owner_dir = safe_join(root, owner)
    except ValueError as exc:
        raise FileNotFoundError("invalid owner") from exc
    _ensure_owner_scaffold(owner, owner_dir)
    return owner_dir


def load_transactions(
    owner: str,
    accounts_root: Optional[Path] = None,
    *,
    scaffold_missing: bool = False,
) -> List[Dict[str, Any]]:
    """Load all transactions for ``owner`` sorted by date.

    By default the function now raises :class:`FileNotFoundError` when the owner
    directory is absent.  Administrative callers that want to bootstrap a new
    owner can opt-in to scaffolding by passing ``scaffold_missing=True``.

    """
    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = Path(accounts_root) if accounts_root else paths.accounts_root
    try:
        owner_dir = safe_join(root, owner)
    except ValueError as exc:
        raise FileNotFoundError("invalid owner") from exc
    if not owner_dir.exists():
        if not scaffold_missing:
            raise FileNotFoundError(owner_dir)
        # Callers opting to scaffold missing owners expect the function to
        # return an empty transaction list without mutating the filesystem.
        # ``ensure_owner_scaffold`` remains available to explicitly create the
        # default structure when desired.
        return []

    _ensure_owner_scaffold(owner, owner_dir)

    results: List[Dict[str, Any]] = []
    for path in owner_dir.glob("*_transactions.json"):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        acct = data.get("account_type", path.stem.replace("_transactions", ""))
        for t in data.get("transactions", []):
            results.append({"account": acct, **t})

    def sort_key(tx: Dict[str, Any]):
        d = _parse_date(tx.get("date"))
        return d or date.min

    results.sort(key=sort_key)
    return results
