"""OAuth2 client for the Moneyhub Open Banking API.

Implements the access method and auth flow decided in
``docs/moneyhub-integration.md`` (issue #2749): the official Moneyhub API
(OAuth2/OIDC, ``transactions:read`` scope), never scraping
``client.moneyhub.co.uk``. This module is a thin, stateless HTTP wrapper --
it does not know how tokens are stored; see
:mod:`backend.common.moneyhub_tokens` for the per-owner token persistence
that sits above it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from backend.common.url_validator import validate_external_url

log = logging.getLogger("integrations.moneyhub")


class MoneyhubAPIError(Exception):
    """Raised when a Moneyhub API call fails."""


@dataclass
class MoneyhubClient:
    """Adapter for the Moneyhub Open Banking transactions API.

    Only the subset needed to refresh a token and pull transactions is
    implemented -- registering the OAuth2 client and completing the initial
    user-consent authorization-code exchange is a one-off, human-driven step
    (see ``docs/moneyhub-integration.md#handoff-to-a-human``), not something
    this adapter automates.
    """

    client_id: str
    client_secret: str
    base_url: str = "https://api.moneyhub.co.uk"
    timeout: int = 10

    def _headers(self, access_token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {access_token}"}

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Exchange ``refresh_token`` for a new access/refresh token pair.

        Returns the raw token response (``access_token``, ``refresh_token``,
        ``expires_in``, ...) for the caller to persist -- this adapter has no
        opinion on storage, see :mod:`backend.common.moneyhub_tokens`.
        """
        url = f"{self.base_url}/oidc/token"
        validate_external_url(url)
        try:
            resp = requests.post(
                url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=self.timeout,
                allow_redirects=False,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise MoneyhubAPIError(f"Token refresh failed: {exc}") from exc

    def fetch_transactions(
        self, access_token: str, *, account_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch raw transaction records for the consented accounts.

        ``account_id`` narrows the pull to a single connected account;
        omitted, Moneyhub returns transactions across every account the
        owner has consented to share. Field mapping into AllotMint's
        ``Transaction`` model happens separately -- see
        :mod:`backend.importers.moneyhub_api`.
        """
        url = f"{self.base_url}/transactions"
        validate_external_url(url)
        params: Dict[str, str] = {}
        if account_id:
            params["accountId"] = account_id

        try:
            resp = requests.get(
                url,
                params=params,
                headers=self._headers(access_token),
                timeout=self.timeout,
                allow_redirects=False,
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            raise MoneyhubAPIError(f"Transaction fetch failed: {exc}") from exc

        if isinstance(payload, dict):
            return payload.get("data", payload.get("transactions", []))
        return payload
