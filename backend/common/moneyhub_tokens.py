"""Per-owner Moneyhub OAuth token storage.

Follows the secret storage decision in
``docs/moneyhub-integration.md``: each owner's token set (access token,
refresh token, expiry, connected account ids) is one JSON blob under an
``ssm://`` parameter -- ``/allotmint/moneyhub/tokens/{owner}`` by default,
loaded through the existing pluggable :func:`backend.common.storage.get_storage`
abstraction rather than a new secret-loading mechanism. Refresh happens
lazily on read (check expiry, refresh if needed, write back), consistent
with the rest of the backend having no background workers.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

from backend.common.storage import get_storage
from backend.integrations.moneyhub_api import MoneyhubAPIError, MoneyhubClient

_DEFAULT_URI_TEMPLATE = "ssm:///allotmint/moneyhub/tokens/{owner}"


class MoneyhubAuthError(Exception):
    """Raised when an owner has no stored Moneyhub consent to import against."""


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str
    expires_at: float
    account_ids: List[str] = field(default_factory=list)

    def is_expired(self, *, skew_seconds: int = 60) -> bool:
        """True once ``expires_at`` is within ``skew_seconds`` of now."""
        return time.time() >= (self.expires_at - skew_seconds)

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "account_ids": self.account_ids,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TokenSet":
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=data["expires_at"],
            account_ids=list(data.get("account_ids") or []),
        )


def _storage_uri(owner: str) -> str:
    template = os.environ.get("MONEYHUB_TOKENS_STORAGE_URI", _DEFAULT_URI_TEMPLATE)
    return template.format(owner=owner)


def load_token_set(owner: str) -> Optional[TokenSet]:
    """Return the stored token set for ``owner``, or ``None`` if absent."""
    data = get_storage(_storage_uri(owner)).load()
    if not data:
        return None
    return TokenSet.from_dict(data)


def save_token_set(owner: str, token_set: TokenSet) -> None:
    """Persist ``token_set`` for ``owner``."""
    get_storage(_storage_uri(owner)).save(token_set.to_dict())


def get_valid_access_token(owner: str, client: MoneyhubClient) -> str:
    """Return a usable access token for ``owner``, refreshing if needed.

    Raises:
        MoneyhubAuthError: no token set is stored for ``owner`` (they have
            not completed the Moneyhub consent flow), or the stored refresh
            token has been rejected by Moneyhub.
    """
    token_set = load_token_set(owner)
    if token_set is None:
        raise MoneyhubAuthError(f"No Moneyhub consent stored for owner '{owner}'")

    if not token_set.is_expired():
        return token_set.access_token

    try:
        refreshed = client.refresh_access_token(token_set.refresh_token)
    except MoneyhubAPIError as exc:
        raise MoneyhubAuthError(
            f"Moneyhub token refresh failed for owner '{owner}': {exc}"
        ) from exc

    new_token_set = TokenSet(
        access_token=refreshed["access_token"],
        refresh_token=refreshed.get("refresh_token", token_set.refresh_token),
        expires_at=time.time() + refreshed.get("expires_in", 3600),
        account_ids=token_set.account_ids,
    )
    save_token_set(owner, new_token_set)
    return new_token_set.access_token
