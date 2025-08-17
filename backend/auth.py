from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import boto3
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt


security = HTTPBearer(auto_error=False)
REGION = os.getenv("AWS_REGION")
SECRET_NAME = os.getenv("COGNITO_SECRET_NAME")


@dataclass
class CognitoSettings:
    user_pool_id: str
    app_client_id: str


@lru_cache()
def _load_settings() -> Optional[CognitoSettings]:
    """Fetch Cognito configuration from AWS Secrets Manager.

    The secret must contain a JSON object with ``user_pool_id`` and
    ``app_client_id`` fields. When the secret cannot be loaded (e.g. in local
    development) ``None`` is returned and authentication is bypassed.
    """

    if not (REGION and SECRET_NAME):
        return None
    try:
        client = boto3.client("secretsmanager", region_name=REGION)
        resp = client.get_secret_value(SecretId=SECRET_NAME)
        data = json.loads(resp.get("SecretString") or "{}")
        return CognitoSettings(
            user_pool_id=data["user_pool_id"],
            app_client_id=data["app_client_id"],
        )
    except Exception:
        return None


@lru_cache()
def _load_jwks():
    settings = _load_settings()
    if not settings:
        return []
    url = (
        f"https://cognito-idp.{REGION}.amazonaws.com/{settings.user_pool_id}/.well-known/jwks.json"
    )
    resp = httpx.get(url, timeout=5.0)
    resp.raise_for_status()
    return resp.json().get("keys", [])


def _rsa_key(kid: str):
    for key in _load_jwks():
        if key.get("kid") == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    """Validate a JWT from AWS Cognito and return its claims.

    When Cognito settings are not configured the function returns a dummy user
    allowing the API to operate in development and tests.
    """

    settings = _load_settings()
    if not settings:
        return {"sub": "anonymous"}

    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = credentials.credentials
    try:
        headers = jwt.get_unverified_header(token)
        rsa_key = _rsa_key(headers.get("kid"))
        issuer = f"https://cognito-idp.{REGION}.amazonaws.com/{settings.user_pool_id}"
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            audience=settings.app_client_id,
            issuer=issuer,
        )
        return payload
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
