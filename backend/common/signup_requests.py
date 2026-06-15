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
import secrets
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_TOKEN_TTL = timedelta(days=7)
_MAX_NAME_LEN = 200
_MAX_EMAIL_LEN = 320  # RFC 5321 maximum length of a forward-path address
_MAX_NOTE_LEN = 2000


class SignupValidationError(ValueError):
    """Raised when a signup request payload fails validation."""


class SignupTokenError(Exception):
    """Base class for failures when consuming an approval/reject token."""


class RequestNotFound(SignupTokenError):
    """Raised when no pending request matches the supplied id."""


class TokenInvalid(SignupTokenError):
    """Raised when the supplied token does not match the stored hash."""


class RequestExpired(SignupTokenError):
    """Raised when the request's approval window has elapsed."""


class RequestAlreadyProcessed(SignupTokenError):
    """Raised when the request has already been approved or rejected.

    This is what makes approval single-use: a consumed token cannot
    re-provision or change the request a second time.
    """


def _looks_like_email(email: str) -> bool:
    """Cheap, linear-time sanity check for an email address.

    Deliberately permissive: we only guard against obviously malformed input
    (the real check is that a human at the address can act on the admin
    notification). Implemented with string operations rather than a regex to
    avoid catastrophic backtracking (ReDoS) on adversarial input.
    """

    if any(ch.isspace() for ch in email) or email.count("@") != 1:
        return False
    local, _, domain = email.partition("@")
    if not local or not domain:
        return False
    if domain.startswith(".") or domain.endswith(".") or "." not in domain:
        return False
    return ".." not in domain


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
    if len(email) > _MAX_EMAIL_LEN or not _looks_like_email(email):
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


_VALID_REQUEST_ID = set("0123456789abcdef")


def _request_path(request_id: str, store_dir: Path) -> Path | None:
    """Return the on-disk path for ``request_id`` or ``None`` if malformed.

    Request ids are 32-char lowercase hex (``secrets.token_hex(16)``); anything
    else is rejected outright so a hostile id cannot escape ``store_dir`` via
    path traversal.
    """

    if not request_id or len(request_id) > 64:
        return None
    if any(ch not in _VALID_REQUEST_ID for ch in request_id):
        return None
    return Path(store_dir) / f"{request_id}.json"


def load_request(request_id: str, store_dir: Path) -> SignupRequest | None:
    """Load the persisted request for ``request_id`` or ``None`` if absent."""

    path = _request_path(request_id, store_dir)
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return SignupRequest(**data)
    except TypeError:
        # Stored shape no longer matches the dataclass; treat as unusable.
        return None


def _is_expired(record: SignupRequest, now: datetime) -> bool:
    try:
        expires = datetime.fromisoformat(record.expires_at)
    except ValueError:
        # A request we cannot date is treated as expired rather than usable.
        return True
    return now >= expires


def validate_request(
    request_id: str,
    token: str,
    store_dir: Path,
    *,
    now: datetime | None = None,
) -> SignupRequest:
    """Return the pending request for a valid token without mutating it.

    The token is verified by hashing it and comparing to the stored
    ``token_sha256`` with a constant-time comparison. The request must still be
    ``pending`` and unexpired. Raises a :class:`SignupTokenError` subclass on
    every failure so the caller can map each to an unambiguous response.

    This performs no write, so callers can validate, do irreversible work (e.g.
    provisioning), and only then :func:`consume_request` to burn the token.
    """

    moment = now or datetime.now(timezone.utc)
    record = load_request(request_id, store_dir)
    if record is None:
        raise RequestNotFound("no such request")
    if not token or not secrets.compare_digest(record.token_sha256, hash_token(token)):
        raise TokenInvalid("token does not match")
    if record.status != "pending":
        raise RequestAlreadyProcessed(f"request already {record.status}")
    if _is_expired(record, moment):
        raise RequestExpired("approval window has elapsed")
    return record


def consume_request(
    request_id: str,
    token: str,
    store_dir: Path,
    *,
    new_status: str,
    now: datetime | None = None,
) -> SignupRequest:
    """Validate an approval token and atomically move the request to ``new_status``.

    On success the request's status is rewritten so the token cannot be reused
    (single-use); reusing it then raises :class:`RequestAlreadyProcessed`.
    """

    if new_status not in {"approved", "rejected"}:
        raise ValueError(f"invalid status: {new_status!r}")

    record = validate_request(request_id, token, store_dir, now=now)
    updated = replace(record, status=new_status)
    _persist(updated, store_dir)
    logger.info("Signup request %s moved to %s", record.id, new_status)
    return updated
