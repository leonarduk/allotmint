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
from urllib.parse import parse_qs, urljoin, urlsplit

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
        self,
        access_token: str,
        *,
        account_id: Optional[str] = None,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """Fetch raw transaction records for the consented accounts.

        ``account_id`` narrows the pull to a single connected account;
        omitted, Moneyhub returns transactions across every account the
        owner has consented to share. Field mapping into AllotMint's
        ``Transaction`` model happens separately -- see
        :mod:`backend.importers.moneyhub_api`.

        ``max_pages`` bounds the number of responses followed when Moneyhub
        supplies a next-page URL. It defaults to 10 to protect callers from a
        malformed or cyclic pagination chain.
        """
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")

        url = f"{self.base_url}/transactions"
        params: Dict[str, str] = {}
        if account_id:
            params["accountId"] = account_id

        transactions: List[Dict[str, Any]] = []
        visited_urls = set()
        for _ in range(max_pages):
            if url in visited_urls:
                break
            visited_urls.add(url)
            payload, response_headers = self._fetch_transaction_page(url, params, access_token)

            if isinstance(payload, dict):
                page_transactions = payload.get("data")
                if page_transactions is None:
                    page_transactions = payload.get("transactions", [])
                transactions.extend(page_transactions)
            else:
                transactions.extend(payload)

            next_url = self._next_page_url(payload, response_headers)
            if not next_url:
                break
            url = urljoin(url, next_url)
            params = self._account_filter_params(url, account_id)

        return transactions

    @staticmethod
    def _account_filter_params(url: str, account_id: Optional[str]) -> Dict[str, str]:
        """Preserve an account filter unless the page URL already contains it."""
        if not account_id or "accountId" in parse_qs(urlsplit(url).query, keep_blank_values=True):
            return {}
        return {"accountId": account_id}

    def _fetch_transaction_page(self, url: str, params: Dict[str, str], access_token: str) -> tuple[Any, Any]:
        """Fetch and decode one validated transaction page."""
        validate_external_url(url)
        try:
            response = requests.get(
                url,
                params=params,
                headers=self._headers(access_token),
                timeout=self.timeout,
                allow_redirects=False,
            )
            response.raise_for_status()
            return response.json(), getattr(response, "headers", {})
        except requests.RequestException as exc:
            raise MoneyhubAPIError(f"Transaction fetch failed: {exc}") from exc

    @staticmethod
    def _next_page_url(payload: Any, headers: Any) -> Optional[str]:
        """Return a next-page URL from common Moneyhub response formats."""
        if isinstance(payload, dict):
            candidates = [payload.get("next")]
            for key in ("links", "pagination"):
                metadata = payload.get(key)
                if isinstance(metadata, dict):
                    candidates.append(metadata.get("next"))
            for candidate in candidates:
                if isinstance(candidate, str) and candidate:
                    return candidate
                if isinstance(candidate, dict):
                    href = candidate.get("href")
                    if isinstance(href, str) and href:
                        return href

        link_header = headers.get("Link", "") if hasattr(headers, "get") else ""
        for link in link_header.split(","):
            parts = [part.strip() for part in link.split(";")]
            if len(parts) > 1 and 'rel="next"' in parts[1:] and parts[0].startswith("<"):
                return parts[0][1:-1]
        return None
