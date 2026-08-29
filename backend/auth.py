"""Authentication helpers using Google ID tokens."""

from __future__ import annotations

import inspect
import logging
import os
import secrets
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Set, Tuple, cast
from urllib.parse import urlparse

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from google.auth.transport import requests
from google.oauth2 import id_token

try:
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:  # pragma: no cover - botocore is optional in tests

    class BotoCoreError(Exception):
        """Fallback when botocore isn't installed."""

    class ClientError(Exception):
        """Fallback when botocore isn't installed."""


from backend.common.data_loader import DATA_BUCKET_ENV, PLOTS_PREFIX, load_person_metadata, resolve_paths
from backend.config import config, local_login_identity
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET")
_testing = os.getenv("TESTING")
if not SECRET_KEY:
    if (
        config.disable_auth
        or _testing
        or (os.getenv("APP_ENV") or (config.app_env or "")).lower() not in {"production", "aws"}
    ):
        logger.warning("JWT_SECRET not set; using ephemeral secret for development")
        SECRET_KEY = secrets.token_urlsafe(32)
    else:
        raise RuntimeError("JWT_SECRET environment variable is required")
ALGORITHM = "HS256"

# Sentinel email the ``/token*`` endpoints in ``backend/app.py`` issue for every
# login when ``config.disable_auth`` is true, regardless of what credentials (if
# any) were presented. A backend JWT carrying this ``sub`` is therefore always
# self-issued by this same process, never a genuine external identity.
DISABLE_AUTH_STUB_EMAIL = "user@example.com"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Context variable storing the username of the authenticated user.
# This allows downstream helpers to detect whether a request is
# authenticated without needing to thread the username through
# every function call.
current_user: ContextVar[str | None] = ContextVar("current_user", default=None)

# Request-scoped marker set alongside ``current_user`` whenever the resolved
# identity came from a demo-scoped token (see decode_demo_token/DEMO_SCOPE
# below) rather than a real Google/Cognito/backend-JWT login. Downstream
# enforcement (the write-blocking gate and the owner-scoping gate, #7407/
# #7408) reads this via is_demo_request() to decide whether the current
# request is allowed to mutate anything or reach any owner other than the
# configured demo owner.
#
# It is explicitly reset to False at the top of both get_current_user() and
# get_active_user() on *every* request, demo or not -- never left to the
# ContextVar default. A Lambda execution environment can be reused across
# invocations, so relying on the default here would risk a previous demo
# request's ``True`` leaking into a later, unrelated request (fail-open);
# resetting on every entry keeps this fail-closed instead (#7406).
demo_readonly: ContextVar[bool] = ContextVar("demo_readonly", default=False)


def is_demo_request() -> bool:
    """Return whether the current request resolved via a demo-scoped token."""

    return demo_readonly.get()


def _emails_for_person_meta(meta: Any) -> Set[str]:
    """Return the lower-cased owner email plus any viewer emails from ``meta``.

    Mirrors :func:`backend.common.authz._allowed_identities`, which grants
    per-owner access to both the owner's own email and its ``viewers`` list.
    ``_allowed_emails`` must recognise the same set at login/identity-resolution
    time, otherwise a legitimate viewer (allowed by ``ensure_owner_access``)
    would be rejected earlier with a 403 "Unauthorized email" before ever
    reaching that per-owner check (#5215).
    """

    if meta is None:
        return set()
    emails: Set[str] = set()
    email = getattr(meta, "email", None)
    if isinstance(email, str) and email.strip():
        emails.add(email.strip().lower())
    viewers = getattr(meta, "viewers", None)
    if isinstance(viewers, list):
        emails.update(viewer.strip().lower() for viewer in viewers if isinstance(viewer, str) and viewer.strip())
    return emails


def _configured_allowed_emails() -> Set[str]:
    """Return the bootstrap allowlist from ``config.allowed_emails``.

    Sourced from ``config.lambda.yaml``'s ``auth.allowed_emails`` (or the
    ``ALLOWED_EMAILS`` env var, which overrides it -- see
    :func:`backend.config.load_config`). Unlike the S3/local-provisioned
    account emails below, this set is always available even before any owner
    account has been created, so it lets a deployment's designated owner(s)
    authenticate on a fresh deployment with zero provisioned accounts (#6130).
    """

    configured = getattr(config, "allowed_emails", None)
    if not configured:
        return set()
    return {email.strip().lower() for email in configured if isinstance(email, str) and email.strip()}


def _allowed_emails() -> Set[str]:
    """Return the set of configured account emails.

    Includes both each owner's own email and their configured viewer emails
    (see :func:`_emails_for_person_meta`), so identity resolution accepts the
    same callers ``ensure_owner_access`` would later authorize for that owner.
    Also always includes :func:`_configured_allowed_emails`, the deployment's
    bootstrap allowlist, so the owner(s) can authenticate even before any
    account has been provisioned.

    When running in AWS, owner metadata is loaded from S3. If this request
    fails, the exception is logged and the bootstrap allowlist alone is
    returned (rather than clearing it) so the owner is not locked out by a
    transient S3 error.
    """

    emails: Set[str] = _configured_allowed_emails()

    if config.app_env == "aws":
        owners: Set[str] = set()
        bucket = os.getenv(DATA_BUCKET_ENV)
        if bucket:
            try:
                import boto3  # type: ignore

                s3 = boto3.client("s3")
                token: str | None = None
                while True:
                    params = {"Bucket": bucket, "Prefix": PLOTS_PREFIX}
                    if token:
                        params["ContinuationToken"] = token
                    resp = s3.list_objects_v2(**params)
                    for item in resp.get("Contents", []):
                        key = item.get("Key", "")
                        if not key.lower().endswith(".json"):
                            continue
                        if not key.startswith(PLOTS_PREFIX):
                            continue
                        rel = key[len(PLOTS_PREFIX) :]
                        owner = rel.split("/")[0]
                        if owner:
                            owners.add(owner)
                    if resp.get("IsTruncated"):
                        token = resp.get("NextContinuationToken")
                    else:
                        break
            except (BotoCoreError, ClientError):
                logger.exception("Failed to list allowed emails from S3")
                return emails
        for owner in owners:
            try:
                meta = load_person_metadata(owner)
            except Exception:
                meta = None
            emails |= _emails_for_person_meta(meta)
        return emails

    # Determine the accounts root from configuration. Prefer the explicitly
    # configured path and fall back to the default resolution logic. Relative
    # paths are resolved against the repository root so ``config.accounts_root``
    # can be specified as a simple "data/accounts" style path.
    if config.accounts_root:
        root = Path(config.accounts_root).expanduser()
        if not root.is_absolute():
            paths = resolve_paths(config.repo_root, None)
            root = (paths.repo_root / root).resolve()
    else:
        root = resolve_paths(config.repo_root, None).accounts_root

    if not root.exists():
        logger.warning("Accounts root %s does not exist", root)
        return emails

    for owner_dir in root.iterdir():
        if not owner_dir.is_dir():
            continue
        try:
            meta = load_person_metadata(owner_dir.name, data_root=root)
        except Exception:
            meta = None
        emails |= _emails_for_person_meta(meta)
    return emails


def authenticate_user(id_token_str: str) -> Optional[str]:
    """Return the email for a valid ID token or ``None`` if rejected."""

    # ``verify_google_token`` performs all validation, including ensuring the
    # email is present in the accounts directory.  It raises an ``HTTPException``
    # when the token is invalid or the email is not authorised.
    return verify_google_token(id_token_str)


DEFAULT_TOKEN_EXPIRE_MINUTES = 15


def create_access_token(email: str, expires_delta: timedelta | None = None) -> str:
    """Create a JWT for the given email."""

    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta is not None else timedelta(minutes=DEFAULT_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["exp"]},
        )
        # A demo-scoped token (see create_demo_access_token/DEMO_SCOPE below) is
        # signed with the same SECRET_KEY/ALGORITHM as a normal backend JWT, so
        # it verifies successfully here. Without this check its (deliberately
        # absent, but not guaranteed-absent-forever) ``sub`` claim would be
        # handed straight back to callers such as _user_from_token and
        # _resolve_identity_when_auth_disabled, which treat any non-empty
        # return value as a fully authenticated real user. Rejecting every
        # demo-scoped token here — regardless of what else it carries — is the
        # single control that keeps the demo-link primitive from becoming an
        # authentication bypass (#7402, #7405).
        if payload.get("scope") == DEMO_SCOPE:
            return None
        return payload.get("sub")
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        ) from exc
    except jwt.PyJWTError:
        return None


# --- Demo-scoped read-only token (#7402) -----------------------------------
#
# A distinct token "kind" that grants read-only access to a single, explicitly
# designated demo owner without going through Google/Cognito login. Minting
# and verifying it is entirely self-contained in this section: nothing here
# is wired into get_current_user, ensure_owner_access, or any route yet (see
# #7406+). The one cross-cutting change is the DEMO_SCOPE guard added to
# decode_token() above, which ensures a demo token can never be mistaken for
# a normal authenticated user by any pre-existing code path.

DEMO_SCOPE = "demo-readonly"

DEFAULT_DEMO_TOKEN_EXPIRE_HOURS = 72


@dataclass(frozen=True)
class DemoTokenClaims:
    """Verified claims carried by a demo-scoped token."""

    owner: str
    scope: str


def create_demo_access_token(owner: str, expires_delta: timedelta | None = None) -> str:
    """Sign a short-lived, read-only demo token scoped to ``owner``.

    Deliberately does not emit a ``sub`` claim (or any other claim a normal
    identity-resolution path treats as an email/username) — see the
    DEMO_SCOPE guard in decode_token(). Signed with the same SECRET_KEY/
    ALGORITHM as backend/auth.py's other JWTs so it can be verified the same
    way, but it is only ever accepted by decode_demo_token().
    """

    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("owner must be a non-empty string")

    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta is not None else timedelta(hours=DEFAULT_DEMO_TOKEN_EXPIRE_HOURS)
    )
    payload = {"scope": DEMO_SCOPE, "owner": owner.strip(), "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_demo_token(token: str) -> DemoTokenClaims | None:
    """Verify ``token`` as a demo-scoped token, or return ``None``.

    Returns ``None`` — never raises — for a token that is simply not a demo
    token (wrong scope, wrong/missing owner, bad signature, or expired), so
    callers can chain this after/alongside decode_token() without a
    try/except. An expired demo token is rejected explicitly rather than
    left to work forever.
    """

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["exp"]},
        )
    except jwt.PyJWTError:
        return None

    if payload.get("scope") != DEMO_SCOPE:
        return None

    owner = payload.get("owner")
    if not isinstance(owner, str) or not owner.strip():
        return None

    return DemoTokenClaims(owner=owner.strip(), scope=DEMO_SCOPE)


# Claim names surfaced by the admin /whoami debug endpoint. Deliberately a
# fixed allowlist so the raw token and any unexpected/sensitive claims are
# never echoed back — see describe_token and GET /whoami in backend/app.py.
WHOAMI_CLAIM_FIELDS: Tuple[str, ...] = ("sub", "email", "exp", "iss", "token_use", "aud")


def _unverified_claims(token: str) -> dict[str, Any]:
    """Return a JWT's payload WITHOUT verifying its signature.

    Used only by the admin-gated /whoami diagnostic to report what the backend
    decodes from the presented token. For Cognito tokens the API Gateway
    authorizer has already verified the signature upstream; here we only need
    the claim values for observability, not to establish trust. Returns an
    empty mapping when the token is not a decodable JWT.
    """

    try:
        payload = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return {}
    return payload if isinstance(payload, dict) else {}


def describe_token(token: str | None) -> dict[str, Any]:
    """Return an admin-only diagnostic view of the presented bearer token.

    Reports whether a token was presented, a fixed allowlist of decoded claims
    (never the raw token), and whether the token's email matches the backend
    allowed-emails set. The email claim is preferred; app-signed backend JWTs
    carry the email in ``sub`` instead, so that is used as a fallback.
    """

    if not isinstance(token, str) or not token:
        return {"token_present": False, "claims": {}, "allowed_email_match": False}

    payload = _unverified_claims(token)
    if not payload:
        # Malformed/undecodable token: no claims to report, rather than a
        # fixed allowlist of keys all mapped to None.
        return {"token_present": True, "claims": {}, "allowed_email_match": False}

    claims = {field: payload.get(field) for field in WHOAMI_CLAIM_FIELDS}

    email = payload.get("email") or payload.get("sub")
    allowed_email_match = False
    if isinstance(email, str) and email:
        allowed_email_match = email.lower() in _allowed_emails()

    return {
        "token_present": True,
        "claims": claims,
        "allowed_email_match": allowed_email_match,
    }


def _user_from_token(token: str | None) -> str:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    email = decode_token(token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return email


def _identity_from_unverified_token(token: str) -> str | None:
    """Return the ``email``/``sub`` claim from ``token`` without checking its signature.

    Only called when ``config.disable_auth`` is true and ``decode_token`` (the
    backend's own HS256 verifier) could not decode the token. In that
    configuration the token is a Cognito ID token whose signature and
    audience API Gateway's JWT authorizer already validated before this
    Lambda ever ran (see docs/AUTH.md), so re-deriving the claims here without
    re-checking the signature is safe — it is not the first check performed.
    """
    claims = _unverified_claims(token)
    email = claims.get("email") or claims.get("sub")
    return email if isinstance(email, str) and email else None


def _resolve_identity_when_auth_disabled(token: str | None) -> str | None:
    """Resolve the caller's identity when ``config.disable_auth`` is true.

    A present token is trusted to have already been verified upstream: either
    it is an app-signed backend JWT (Google flow), or a Cognito ID token
    validated by API Gateway's JWT authorizer before invoking this Lambda
    (Cognito flow). Either way its claimed email must belong to a provisioned
    account — an unrecognized email is rejected explicitly rather than
    silently collapsing every caller into the shared local/demo identity.
    Only a request with no token at all (bare local dev, no client-side auth)
    falls back to the configured local login identity.

    One exception: when ``decode_token`` cannot verify the token's signature,
    the unverified claims are checked for :data:`DISABLE_AUTH_STUB_EMAIL`. In
    disable_auth mode ``SECRET_KEY`` is an ephemeral value regenerated on every
    process restart (see the module-level warning above), so a browser holding
    a JWT issued by a previous run always fails signature verification here
    even though it is unmistakably our own token, not a foreign caller — the
    ``/token*`` endpoints only ever sign that one sentinel email while auth is
    disabled. Treating that specific case as equivalent to "no token" (rather
    than a hard 403) fixes anonymous/demo mode expiring on every backend
    restart while a stale token is cached client-side (#5484); genuinely
    unrecognized emails (e.g. a real, unprovisioned Cognito identity) are
    still rejected below.
    """
    if isinstance(token, str) and token:
        user = decode_token(token)
        if user:
            return user
        email = _identity_from_unverified_token(token)
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )
        if email.lower() == DISABLE_AUTH_STUB_EMAIL:
            identity = local_login_identity()
            return identity
        if email.lower() not in _allowed_emails():
            logger.warning(
                "Unauthorized identity on disable_auth path for %s",
                sanitise_log_value(email),
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized email")
        return email
    identity = local_login_identity()
    if identity is None:
        return None
    return identity


def _resolve_demo_request(token: str | None) -> str | None:
    """If ``token`` is a demo-scoped token, validate and resolve it.

    Returns the configured demo owner id (having already set ``current_user``
    and ``demo_readonly``) when ``token`` is a valid demo-scoped token for the
    configured demo owner. Returns ``None`` -- without touching either
    ContextVar -- when ``token`` is simply not a demo token at all, so callers
    fall through to their normal resolution path unchanged.

    Raises ``HTTPException(401)`` for a demo token that is well-formed but
    unusable: the demo link is disabled (``config.demo_link_enabled`` is
    false, the real kill switch -- not just a mint-side toggle), or the
    token's ``owner`` claim does not match ``config.demo_link_owner`` (e.g. a
    token minted for a different owner, or minted before the config changed).
    This is a sibling code path to :func:`_resolve_identity_when_auth_disabled`,
    not a variant of it -- ``disable_auth``/``DISABLE_AUTH_STUB_EMAIL``
    semantics are untouched here.
    """

    if not token:
        return None
    claims = decode_demo_token(token)
    if claims is None:
        return None
    if not config.demo_link_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    if claims.owner != config.demo_link_owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    current_user.set(claims.owner)
    demo_readonly.set(True)
    return claims.owner


async def get_current_user(token: str | None = Depends(oauth2_scheme)) -> str:
    """Return the authenticated user extracted from the bearer token."""

    # Reset on every request, demo or not -- see the demo_readonly ContextVar
    # docstring above for why this must not rely on the ContextVar default.
    demo_readonly.set(False)

    token_str = token if isinstance(token, str) else None
    demo_identity = _resolve_demo_request(token_str)
    if demo_identity is not None:
        return demo_identity

    if config.disable_auth:
        identity = _resolve_identity_when_auth_disabled(token)
        if identity:
            current_user.set(identity)
            return identity
        # No token was presented and no local identity is configured — there is
        # no caller to authenticate. Raise explicitly rather than falling
        # through to _user_from_token(None), whose own "no token" rejection
        # happens to produce the same status code today but is not a
        # substitute for this terminal case (#4795). The detail message is
        # deliberately actionable (rather than a generic "Invalid
        # authentication credentials") since this specific case is the
        # out-of-the-box state of a fresh local checkout with disable_auth=true
        # and no override picked yet — a bare 401 left first-time users with no
        # indication that Support -> Local login override needed configuring
        # (#6058).
        current_user.set(None)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "No local login override is configured. Go to Support -> "
                "Local login override and select a user to continue in local/demo mode."
            ),
        )
    return _user_from_token(token_str)


def _iter_override_mappings(request: Request) -> list[Mapping[Any, Callable[..., Any]]]:
    """Return override mappings in FastAPI's resolution order."""

    try:
        app_owner = getattr(request, "app")
    except KeyError:
        app_owner = None
    owners = [app_owner]
    app = owners[0]
    router = getattr(app, "router", None) if app is not None else None
    if router is not None:
        owners.append(router)

    seen_mappings: Set[int] = set()
    mappings: list[Mapping[Any, Callable[..., Any]]] = []

    def _register_mapping(candidate: Any) -> None:
        if candidate is None:
            return
        mapping: Mapping[Any, Callable[..., Any]] | None = None
        if isinstance(candidate, Mapping):
            mapping = cast(Mapping[Any, Callable[..., Any]], candidate)
        elif hasattr(candidate, "get"):
            mapping = cast(Mapping[Any, Callable[..., Any]], candidate)
        if mapping is None:
            return
        mapping_id = id(mapping)
        if mapping_id in seen_mappings:
            return
        seen_mappings.add(mapping_id)
        mappings.append(mapping)

    for owner in owners:
        if owner is None:
            continue
        _register_mapping(getattr(owner, "dependency_overrides", None))

    seen_providers: Set[int] = set()
    queue: list[Any] = []
    for owner in owners:
        if owner is None:
            continue
        queue.append(getattr(owner, "dependency_overrides_provider", None))

    while queue:
        provider = queue.pop()
        if provider is None:
            continue
        provider_id = id(provider)
        if provider_id in seen_providers:
            continue
        seen_providers.add(provider_id)

        _register_mapping(getattr(provider, "dependency_overrides", None))

        nested = getattr(provider, "dependency_overrides_provider", None)
        if not nested:
            continue
        if isinstance(nested, (list, tuple, set, frozenset)):
            queue.extend(nested)
        else:
            queue.append(nested)

    return mappings


def _find_override(request: Request, dependency: Callable[..., Any]) -> Callable[..., Any] | None:
    """Return the override callable for ``dependency`` if configured."""

    targets = {dependency}
    target_identities: set[tuple[str | None, str | None]] = set()

    def _identity(func: Callable[..., Any]) -> tuple[str | None, str | None] | None:
        module = getattr(func, "__module__", None)
        qualname = getattr(func, "__qualname__", None)
        if module is None or qualname is None:
            return None
        return module, qualname

    try:
        unwrapped_dependency = inspect.unwrap(dependency)
    except Exception:  # pragma: no cover - defensive
        unwrapped_dependency = dependency
    else:
        targets.add(unwrapped_dependency)

    for candidate in list(targets):
        identity = _identity(candidate)
        if identity is not None:
            target_identities.add(identity)

    for mapping in _iter_override_mappings(request):
        getter = getattr(mapping, "get", None)
        if callable(getter):
            candidate = getter(dependency)
            if candidate is not None:
                return candidate

        items = getattr(mapping, "items", None)
        if not callable(items):
            continue
        try:
            entries = list(items())
        except Exception:  # pragma: no cover - defensive
            entries = []
        for declared_dependency, override in entries:
            if declared_dependency in targets:
                return override
            identity = _identity(declared_dependency)
            if identity in target_identities:
                return override
            try:
                unwrapped = inspect.unwrap(declared_dependency)
            except Exception:  # pragma: no cover - defensive
                unwrapped = declared_dependency
            if unwrapped in targets:
                return override
            identity = _identity(unwrapped)
            if identity in target_identities:
                return override
    return None


async def _invoke_override(override: Callable[..., Any], *, request: Request, token: str | None) -> Any:
    """Invoke a dependency override supporting ``request``/``token`` kwargs."""

    kwargs: dict[str, Any] = {}
    try:
        signature = inspect.signature(override)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        signature = None

    if signature is not None:
        for name, parameter in signature.parameters.items():
            if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
                continue
            annotation = parameter.annotation
            if name == "request":
                kwargs[name] = request
            elif name == "token":
                kwargs[name] = token
            elif annotation is not inspect._empty:
                try:
                    if issubclass(annotation, Request):  # type: ignore[arg-type]
                        kwargs[name] = request
                except TypeError:  # pragma: no cover - defensive
                    pass
    result = override(**kwargs) if kwargs else override()
    if inspect.isawaitable(result):
        result = await result
    return result


async def resolve_current_user_override(request: Request, *, token: str | None = None) -> Tuple[bool, Any]:
    """Return the configured override result for ``get_current_user`` if any."""

    override = _find_override(request, get_current_user)
    if override is None:
        return False, None
    result = await _invoke_override(override, request=request, token=token)
    return True, result


async def get_active_user(request: Request, token: str | None = Depends(oauth2_scheme)) -> str | None:
    """Return the active user when authentication is enabled.

    When ``config.disable_auth`` is truthy the API allows unauthenticated
    access and this helper returns ``None`` so callers can fall back to a
    shared demo identity.  If a token is supplied while auth is disabled it is
    still validated to support mixed environments where some requests provide
    credentials.

    Tests override :func:`get_current_user` to bypass authentication entirely.
    FastAPI's dependency override mechanism does not automatically propagate to
    helpers such as this one, so we honour any override manually when present
    on the application.  This keeps the production behaviour while ensuring the
    router can be exercised easily in unit tests.
    """

    # Reset on every request, demo or not -- see the demo_readonly ContextVar
    # docstring above for why this must not rely on the ContextVar default.
    demo_readonly.set(False)

    has_override, override_result = await resolve_current_user_override(request, token=token)
    if has_override:
        current_user.set(override_result)
        return override_result

    token_str = token if isinstance(token, str) else None
    demo_identity = _resolve_demo_request(token_str)
    if demo_identity is not None:
        return demo_identity

    if config.disable_auth:
        identity = _resolve_identity_when_auth_disabled(token)
        current_user.set(identity)
        return identity

    user = _user_from_token(token_str)
    current_user.set(user)
    return user


def _email_verified(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return False


def _authorize_email(email: Any, token: str, provider: str) -> str:
    if not isinstance(email, str) or not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email missing")

    allowed = _allowed_emails()
    if not allowed:
        logger.error("No allowed emails configured; rejecting login attempt")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized email")

    if email.lower() not in allowed:
        logger.warning(
            "Unauthorized %s login attempt for %s (token %.8s)",
            provider,
            sanitise_log_value(email),
            sanitise_log_value(token[:8]),
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized email")

    return email


def verify_google_token(token: str) -> str:
    client_id = config.google_client_id
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google client ID not configured",
        )
    try:
        info = id_token.verify_oauth2_token(token, requests.Request(), client_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        ) from exc

    if not _email_verified(info.get("email_verified")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email not verified")

    return _authorize_email(info.get("email"), token, "Google")


def _cognito_issuer_from_unverified_token(token: str) -> str:
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Cognito token",
        ) from exc

    issuer = payload.get("iss")
    if not isinstance(issuer, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cognito issuer missing",
        )
    parsed = urlparse(issuer)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Cognito issuer",
        )
    # Require both the cognito-idp. prefix and the .amazonaws.com suffix to
    # prevent attacker-controlled JWKS endpoints at cognito-idp.attacker.com.
    if not (parsed.hostname.startswith("cognito-idp.") and parsed.hostname.endswith(".amazonaws.com")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unsupported Cognito issuer",
        )
    return issuer.rstrip("/")


_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _get_jwks_client(issuer: str) -> jwt.PyJWKClient:
    if issuer not in _jwks_clients:
        _jwks_clients[issuer] = jwt.PyJWKClient(f"{issuer}/.well-known/jwks.json")
    return _jwks_clients[issuer]


def verify_cognito_token(token: str, client_id: str) -> str:
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cognito client ID missing",
        )

    issuer = _cognito_issuer_from_unverified_token(token)
    try:
        jwks_client = _get_jwks_client(issuer)
        key = jwks_client.get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=issuer,
            options={"require": ["aud", "exp", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Cognito token",
        ) from exc

    if payload.get("token_use") != "id":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Cognito token use",
        )
    if not _email_verified(payload.get("email_verified")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email not verified")
    return _authorize_email(payload.get("email"), token, "Cognito")
