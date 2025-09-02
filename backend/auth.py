"""Authentication helpers using Google ID tokens."""

from __future__ import annotations

import os
from contextvars import ContextVar
from typing import Optional, Set

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from google.auth.transport import requests
from google.oauth2 import id_token

from backend.common.data_loader import (
    DATA_BUCKET_ENV,
    PLOTS_PREFIX,
    load_person_meta,
    resolve_paths,
)
from backend.config import config

SECRET_KEY = os.getenv("JWT_SECRET", "change-me")
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Context variable storing the username of the authenticated user.
# This allows downstream helpers to detect whether a request is
# authenticated without needing to thread the username through
# every function call.
current_user: ContextVar[str | None] = ContextVar("current_user", default=None)


def _allowed_emails() -> Set[str]:
    """Return the set of configured account emails."""

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
            except Exception:
                pass
        for owner in owners:
            try:
                meta = load_person_meta(owner)
            except Exception:
                meta = {}
            email = meta.get("email") if isinstance(meta, dict) else None
            if email:
                emails.add(email.lower())
        return emails

    paths = resolve_paths(config.repo_root, config.accounts_root)
    root = paths.accounts_root
    if root.exists():
        for owner_dir in root.iterdir():
            if not owner_dir.is_dir():
                continue
            meta = load_person_meta(owner_dir.name, data_root=root)
            email = meta.get("email")
            if email:
                emails.add(email.lower())
    return emails


def authenticate_user(id_token_str: str) -> Optional[str]:
    """Return the email for a valid ID token or ``None`` if rejected."""

    email = verify_google_token(id_token_str)
    if not email:
        return None
    if email.lower() not in _allowed_emails():
        return None
    return email


def create_access_token(email: str) -> str:
    """Create a JWT for the given email."""

    return jwt.encode({"sub": email}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    email = decode_token(token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return email


def verify_google_token(token: str) -> str:
    try:
        info = id_token.verify_oauth2_token(token, requests.Request(), config.google_client_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token") from exc

    if not info.get("email_verified"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email not verified")

    email = info.get("email")
    allowed = set(config.allowed_emails or [])
    if email not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized email")
    return email
