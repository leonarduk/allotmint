"""Authentication helpers using Google ID tokens."""

from __future__ import annotations

import os
from typing import Optional, Set

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from backend.common.data_loader import load_person_meta, resolve_paths, list_plots
from backend.config import config

SECRET_KEY = os.getenv("JWT_SECRET", "change-me")
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_google_token(token: str) -> Optional[str]:
    """Verify a Google ID token and return the associated email.

    Returns ``None`` if verification fails for any reason. The implementation
    attempts to use :mod:`google-auth` if available but deliberately swallows
    all errors so tests can patch this function without requiring the
    dependency or network access.
    """

    try:  # pragma: no cover - exercised via tests with monkeypatching
        from google.oauth2 import id_token
        from google.auth.transport import requests

        info = id_token.verify_oauth2_token(token, requests.Request())
        return info.get("email")
    except Exception:
        return None


def _allowed_emails() -> Set[str]:
    """Return the set of configured account emails."""

    emails: Set[str] = set()

    if config.app_env == "aws":
        owners = {p["owner"] for p in list_plots()}
        for owner in owners:
            meta = load_person_meta(owner)
            email = meta.get("email")
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

