import hashlib
import os
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from google.oauth2 import id_token
from google.auth.transport import requests

from backend.config import config

# Simple in-memory user store with hashed passwords

def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

users_db = {
    "testuser": _hash("password"),
}

SECRET_KEY = os.getenv("JWT_SECRET", "change-me")
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def authenticate_user(username: str, password: str) -> Optional[str]:
    hashed = users_db.get(username)
    if not hashed:
        return None
    if _hash(password) != hashed:
        return None
    return username


def create_access_token(username: str) -> str:
    return jwt.encode({"sub": username}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    username = decode_token(token)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return username


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
