"""Owner provisioning for approved signup requests.

Keeps the "grant a login" logic out of the route handler (see
:mod:`backend.routes.signup`). Approving a request must do two things so the
user can actually authenticate:

* scaffold the owner's data directory via
  :func:`backend.common.compliance.ensure_owner_scaffold` (the same path used
  everywhere else — never hand-write the JSON), and
* record the user's email in their ``person.json`` so it becomes part of
  :func:`backend.auth._allowed_emails`, which reads each owner's
  ``person.json`` email from the accounts root.

The owner slug is derived from the request email. If the derived slug is
already taken by a *different* email we pick the next free suffix rather than
overwriting someone else's account.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from backend.common.compliance import ensure_owner_scaffold
from backend.common.path_utils import safe_join
from backend.common.signup_requests import SignupRequest

logger = logging.getLogger(__name__)

# Bounded so a pathological run of collisions can never loop unbounded.
_MAX_SLUG_CANDIDATES = 100


def derive_owner_slug(email: str) -> str:
    """Return a filesystem-safe base owner slug derived from ``email``.

    Uses the local part of the address, lowercased, with any run of
    non-alphanumeric characters collapsed to a single hyphen. Falls back to
    ``"user"`` when nothing usable remains.
    """

    local = email.split("@", 1)[0].lower()
    slug = re.sub(r"[^a-z0-9]+", "-", local).strip("-")
    return slug or "user"


def _read_person_email(owner_dir: Path) -> str:
    """Return the lowercased email stored in ``owner_dir/person.json`` (or "")."""

    person_path = owner_dir / "person.json"
    if not person_path.exists():
        return ""
    try:
        data = json.loads(person_path.read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    email = data.get("email")
    return email.strip().lower() if isinstance(email, str) else ""


def _resolve_owner_slug(email: str, accounts_root: Path) -> str:
    """Pick an owner slug for ``email`` under ``accounts_root``.

    Reuses an existing directory already owned by this email (idempotency) and
    otherwise returns the first free ``base``/``base-2``/``base-3`` ... slug so
    we never clobber a different user's data.
    """

    base = derive_owner_slug(email)
    for suffix in range(1, _MAX_SLUG_CANDIDATES + 1):
        candidate = base if suffix == 1 else f"{base}-{suffix}"
        owner_dir = accounts_root / candidate
        if not owner_dir.exists():
            return candidate
        if _read_person_email(owner_dir) == email:
            return candidate
    raise RuntimeError(f"could not allocate an owner slug for base {base!r}")


def _write_person_identity(owner_dir: Path, email: str, full_name: str) -> None:
    """Merge ``email``/``full_name`` into the scaffolded ``person.json``.

    ``ensure_owner_scaffold`` creates ``person.json`` with empty identity
    fields; this fills them in so :func:`backend.auth._allowed_emails` admits
    the user. Existing keys are preserved.
    """

    person_path = safe_join(owner_dir, "person.json")
    try:
        loaded = json.loads(person_path.read_text())
    except (OSError, json.JSONDecodeError):
        loaded = {}
    if not isinstance(loaded, dict):
        loaded = {}

    loaded["email"] = email
    if full_name and not str(loaded.get("full_name") or "").strip():
        loaded["full_name"] = full_name

    person_path.write_text(json.dumps(loaded, indent=2, sort_keys=True))


def provision_owner(
    record: SignupRequest,
    accounts_root: Path,
    *,
    store: object | None = None,
) -> str:
    """Provision the owner for an approved request and return the owner slug.

    Scaffolds the owner directory under ``accounts_root`` and records the
    request email in ``person.json`` so the user can authenticate. When a
    writable ``store`` is supplied its ``ensure_owner`` is also invoked so the
    deployed writable-store path stays consistent with #4353.
    """

    accounts_root = Path(accounts_root)
    owner = _resolve_owner_slug(record.email, accounts_root)
    owner_dir = ensure_owner_scaffold(owner, accounts_root)
    _write_person_identity(owner_dir, record.email, record.name)

    if store is not None:
        ensure = getattr(store, "ensure_owner", None)
        if callable(ensure):
            ensure(owner)

    logger.info("Provisioned owner %s for approved signup request %s", owner, record.id)
    return owner
