"""Authentication helpers using Google ID tokens."""

from __future__ import annotations

import inspect
import logging
import os
import secrets
from collections.abc import Mapping
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Set, Tuple, cast

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


from backend.common.data_loader import (
    DATA_BUCKET_ENV,
    PLOTS_PREFIX,
    load_person_meta,
    resolve_paths,
)
from backend.config import config

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET")
_testing = os.getenv("TESTING")
if not SECRET_KEY:
    if (
        config.disable_auth
        or _testing
        or (os.getenv("APP_ENV") or (config.app_env or "")).lower()
        not in {"production", "aws"}
    ):
        logger.warning("JWT_SECRET not set; using ephemeral secret for development")
        SECRET_KEY = secrets.token_urlsafe(32)
    else:
        raise RuntimeError("JWT_SECRET environment variable is required")
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Context variable storing the username of the authenticated user.
# This allows downstream helpers to detect whether a request is
# authenticated without needing to thread the username through
# every function call.
current_user: ContextVar[str | None] = ContextVar("current_user", default=None)


def _allowed_emails() -> Set[str]:
    """Return the set of configured account emails.

    When running in AWS, owner metadata is loaded from S3. If this request
    fails, the exception is logged and an empty set is returned so that login
    attempts are rejected cleanly.
    """

    emails: Set[str] = set()

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
                return set()
        for owner in owners:
            try:
                meta = load_person_meta(owner)
            except Exception:
                meta = {}
            email = meta.get("email") if isinstance(meta, dict) else None
            if email:
                emails.add(email.lower())
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
        return set()

    for owner_dir in root.iterdir():
        if not owner_dir.is_dir():
            continue
        try:
            meta = load_person_meta(owner_dir.name, data_root=root)
        except Exception:
            meta = {}
        email = meta.get("email")
        if email:
            emails.add(email.lower())
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
        return payload.get("sub")
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        ) from exc
    except jwt.PyJWTError:
        return None


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


async def get_current_user(token: str | None = Depends(oauth2_scheme)) -> str:
    """Return the authenticated user extracted from the bearer token."""

    return _user_from_token(token)


def _iter_override_mappings(request: Request) -> list[Mapping[Any, Callable[..., Any]]]:
    """Return override mappings in FastAPI's resolution order."""

    owners = [getattr(request, "app", None)]
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


def _find_override(
    request: Request, dependency: Callable[..., Any]
) -> Callable[..., Any] | None:
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


async def _invoke_override(
    override: Callable[..., Any], *, request: Request, token: str | None
) -> Any:
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


async def resolve_current_user_override(
    request: Request, *, token: str | None = None
) -> Tuple[bool, Any]:
    """Return the configured override result for ``get_current_user`` if any."""

    override = _find_override(request, get_current_user)
    if override is None:
        return False, None
    result = await _invoke_override(override, request=request, token=token)
    return True, result


async def get_active_user(
    request: Request, token: str | None = Depends(oauth2_scheme)
) -> str | None:
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

    has_override, override_result = await resolve_current_user_override(
        request, token=token
    )
    if has_override:
        current_user.set(override_result)
        return override_result

    if config.disable_auth:
        if token:
            user = _user_from_token(token)
            current_user.set(user)
            return user
        current_user.set(None)
        return None

    user = _user_from_token(token)
    current_user.set(user)
    return user


def verify_google_token(token: str) -> str:
    client_id = config.google_client_id
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google client ID not configured",
        )
    try:
        info = id_token.verify_oauth2_token(
            token, requests.Request(), client_id
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        ) from exc

    if not info.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Email not verified"
        )

    email = info.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Email missing"
        )

    allowed = _allowed_emails()
    if not allowed:
        logger.error("No allowed emails configured; rejecting login attempt")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized email"
        )

    if email.lower() not in allowed:
        logger.warning(
            "Unauthorized login attempt for %s (token %.8s)",
            email,
            token[:8],
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized email"
        )

    return email
