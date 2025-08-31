import hashlib
import os
from contextvars import ContextVar
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# Simple in-memory user store with hashed passwords

def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

users_db = {
    "testuser": _hash("password"),
}

SECRET_KEY = os.getenv("JWT_SECRET", "change-me")
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Context variable storing the username of the authenticated user.
# This allows downstream helpers to detect whether a request is
# authenticated without needing to thread the username through
# every function call.
current_user: ContextVar[str | None] = ContextVar("current_user", default=None)


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
    # Record the authenticated user for the duration of the request.
    current_user.set(username)
    return username
