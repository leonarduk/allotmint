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

Note: a user who somehow reaches a write endpoint (e.g. ``POST /transactions``
or ``POST /holdings/manual``) without going through the approval flow will have
their account created implicitly by
:meth:`~backend.common.accounts_store.AccountsStore.ensure_owner` — a
minimal scaffold without their email, which means
:func:`backend.auth._allowed_emails` will not admit them until their email is
recorded via this provisioning path.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

from backend.common.compliance import ensure_owner_scaffold
from backend.common.signup_requests import SignupRequest
from backend.logging_setup import sanitise_log_value

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
    """Return the lowercased email stored in ``owner_dir/person.json`` (or "").

    A malformed ``person.json`` is logged and treated as having no email so a
    corrupt file never silently masks an existing account owner.
    """

    person_path = owner_dir / "person.json"
    if not person_path.exists():
        return ""
    try:
        data = json.loads(person_path.read_text())
    except OSError as exc:
        logger.warning("Could not read %s: %s", person_path, exc)
        return ""
    except json.JSONDecodeError as exc:
        logger.warning("Malformed person.json at %s: %s", person_path, exc)
        return ""
    if not isinstance(data, dict):
        logger.warning("person.json at %s is not an object", person_path)
        return ""
    email = data.get("email")
    return email.strip().lower() if isinstance(email, str) else ""


def _resolve_owner_slug(email: str, accounts_root: Path, full_name: str = "") -> str:
    """Atomically claim an owner slug for ``email`` under ``accounts_root``.

    The candidate directory is created with ``mkdir`` (no ``exist_ok``) so two
    concurrent approvals can never both believe the same slug is free. An
    existing directory owned by this same email is reused (idempotent
    re-provision); one owned by a different email is skipped so we never clobber
    another user's data. ``email`` is lowercased to match the normalised form
    stored in ``person.json``.

    ``person.json`` is scaffolded and stamped with the full identity
    (``email`` + ``full_name``) immediately after ``mkdir`` wins, before
    returning. Without this, a second concurrent approval for the *same* email
    that loses the ``mkdir`` race would hit ``FileExistsError`` and find no
    ``person.json`` yet (the winner hadn't written it), read no matching email
    via ``_read_person_email``, and go on to claim a second slug for the same
    person. Writing it here closes that window instead of leaving it to the
    caller's later, non-atomic write.

    If the scaffold or identity write fails, the created directory is removed
    so we never leave an orphan directory behind.
    """

    email = email.strip().lower()
    base = derive_owner_slug(email)
    for suffix in range(1, _MAX_SLUG_CANDIDATES + 1):
        candidate = base if suffix == 1 else f"{base}-{suffix}"
        owner_dir = accounts_root / candidate
        try:
            owner_dir.mkdir(parents=True)
        except FileExistsError:
            # Lost the race or pre-existing: reuse only if it is this email's.
            if _read_person_email(owner_dir) == email:
                return candidate
            continue
        try:
            ensure_owner_scaffold(candidate, accounts_root)
            _write_person_identity(owner_dir, email, full_name)
        except Exception:
            shutil.rmtree(owner_dir, ignore_errors=True)
            raise
        return candidate
    raise RuntimeError(f"could not allocate an owner slug for base {base!r}")


def _write_person_identity(owner_dir: Path, email: str, full_name: str) -> None:
    """Merge ``email``/``full_name`` into the scaffolded ``person.json``.

    ``ensure_owner_scaffold`` creates ``person.json`` with empty identity
    fields; this fills them in so :func:`backend.auth._allowed_emails` admits
    the user. Existing keys are preserved.
    """

    person_path = owner_dir / "person.json"
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
    request email in ``person.json`` so the user can authenticate.
    ``_resolve_owner_slug`` already performs both the scaffold and the
    identity write (with the real ``full_name``) as part of atomically
    claiming the slug, so there is nothing left to do here for a fresh
    or re-provisioned owner. When a writable ``store`` is supplied its
    ``ensure_owner`` is also invoked so the deployed writable-store path
    stays consistent with #4353.
    """

    accounts_root = Path(accounts_root)
    email = record.email.strip().lower()
    owner = _resolve_owner_slug(email, accounts_root, record.name)

    if store is not None:
        ensure = getattr(store, "ensure_owner", None)
        if callable(ensure):
            ensure(owner)

    logger.info(
        "Provisioned owner %s for approved signup request %s",
        sanitise_log_value(owner),
        sanitise_log_value(record.id),
    )
    return owner
