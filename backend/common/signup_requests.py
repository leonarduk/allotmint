"""Domain logic for public account-signup requests.

Keeps validation, token generation, and persistence out of the route handler
(see :mod:`backend.routes.signup`). A signup request records a visitor's
interest in an account and produces an unguessable, expiring approval token.

Only the SHA-256 hash of the approval token is persisted; the plaintext token
is returned once (to be embedded in the admin notification email) and never
stored, so a leak of the request store cannot reconstruct a usable link. The
approval flow (#4352) verifies an inbound token by hashing it and comparing it
to the stored ``token_sha256`` while ``status == "pending"`` and the request
has not expired, giving single-use, time-bound semantics.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Deliberately permissive: we only guard against obviously malformed input.
# RFC-complete email validation is intractable and not required here — the
# real check is that a human at the address can act on the admin notification.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_TOKEN_TTL = timedelta(days=7)
_MAX_NAME_LEN = 200
_MAX_EMAIL_LEN = 320  # RFC 5321 maximum length of a forward-path address
_MAX_NOTE_LEN = 2000


class SignupValidationError(ValueError):
    """Raised when a signup request payload fails validation."""


@dataclass(frozen=True)
class SignupRequest:
    """A persisted pending signup request.

    ``token_sha256`` is the hash of the single-use approval token; the
    plaintext token is never stored on this record.
    """

    id: str
    name: str
    email: str
    note: str
    status: str
    created_at: str
    expires_at: str
    token_sha256: str


def normalise_payload(payload: object) -> tuple[str, str, str]:
    """Validate and normalise a raw signup payload.

    Returns ``(name, email, note)`` with the email lowercased and all fields
    trimmed. Raises :class:`SignupValidationError` on any malformed field.
    """

    if not isinstance(payload, dict):
        raise SignupValidationError("invalid payload")

    name = str(payload.get("name") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    note = str(payload.get("note") or "").strip()

    if not name or len(name) > _MAX_NAME_LEN:
        raise SignupValidationError("invalid name")
    if len(email) > _MAX_EMAIL_LEN or not _EMAIL_RE.match(email):
        raise SignupValidationError("invalid email")
    if len(note) > _MAX_NOTE_LEN:
        raise SignupValidationError("note too long")

    return name, email, note


def hash_token(token: str) -> str:
    """Return the hex SHA-256 digest used to persist an approval token."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def signup_requests_dir(data_root: Path) -> Path:
    """Return the directory holding pending signup requests."""

    return Path(data_root) / "signup_requests"


def create_signup_request(
    name: str,
    email: str,
    note: str,
    store_dir: Path,
    *,
    now: datetime | None = None,
) -> tuple[SignupRequest, str]:
    """Persist a pending request and return it with the plaintext token.

    The returned token is the only time the plaintext exists; callers embed it
    in the admin email and discard it. ``now`` is injectable for tests.
    """

    moment = now or datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    record = SignupRequest(
        id=secrets.token_hex(16),
        name=name,
        email=email,
        note=note,
        status="pending",
        created_at=moment.isoformat(),
        expires_at=(moment + _TOKEN_TTL).isoformat(),
        token_sha256=hash_token(token),
    )
    _persist(record, store_dir)
    return record, token


def _persist(record: SignupRequest, store_dir: Path) -> None:
    """Write ``record`` to ``store_dir`` as ``<id>.json``."""

    directory = Path(store_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record.id}.json"
    path.write_text(json.dumps(asdict(record), indent=2, sort_keys=True))
    logger.info("Recorded pending signup request %s", record.id)
