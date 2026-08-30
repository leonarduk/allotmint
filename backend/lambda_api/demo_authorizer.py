"""API Gateway HTTP API Lambda authorizer for the ``ANY /`` and
``ANY /{proxy+}`` routes (issue #7522).

Replaces ``BackendLambdaStack``'s Cognito ``HttpUserPoolAuthorizer`` on those
two routes. Admits a request when its ``Authorization: Bearer <token>``
header carries EITHER:

- a valid Cognito ID token (``backend.auth.is_cognito_id_token``), matching
  the UI app client or the deploy workflow's smoke-test client audience; or
- a valid demo-scoped, read-only token (``backend.auth.decode_demo_token``)
  minted by ``POST /demo-link`` (see docs/AUTH.md, "Demo link (scoped
  read-only token)").

Before this fix, a demo-scoped token -- signed with the app's own
``JWT_SECRET`` (HS256), never issued by Cognito -- was rejected by API
Gateway's native Cognito JWT authorizer before the backend Lambda ever ran,
so ``backend.auth.decode_demo_token``/``_resolve_demo_request`` were
unreachable on any deployed route besides the handful already registered
with ``HttpNoneAuthorizer``.

This authorizer only checks *structural* token validity (signature, issuer,
expiry, audience/scope) -- it does not re-run the allowed-emails allowlist
check or the demo owner/kill-switch check. Both already run, exactly once,
downstream in the backend Lambda regardless of DISABLE_AUTH (see
``backend/auth.py``'s ``get_current_user``/``_resolve_demo_request``), so
duplicating them here would add cost (an S3-backed lookup on every request)
without adding a security guarantee.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from backend.auth import decode_demo_token, is_cognito_id_token

logger = logging.getLogger(__name__)

_BEARER_PREFIX = "Bearer "


def _bearer_token(event: dict[str, Any]) -> str | None:
    """Extract the raw bearer token from a payload-format-2.0 authorizer event."""

    identity_source = event.get("identitySource") or []
    header_value = identity_source[0] if identity_source else None

    if not isinstance(header_value, str) or not header_value:
        headers = event.get("headers") or {}
        header_value = headers.get("authorization") or headers.get("Authorization")

    if not isinstance(header_value, str) or not header_value:
        return None

    if header_value.startswith(_BEARER_PREFIX):
        return header_value[len(_BEARER_PREFIX) :] or None
    return header_value


def _cognito_client_ids() -> list[str]:
    """Return the configured Cognito app client audiences to accept.

    Sourced from the same env vars BackendLambdaStack injects into this
    authorizer's environment (UI_AUTH_USER_POOL_CLIENT_ID,
    SMOKE_TEST_USER_POOL_CLIENT_ID) -- mirroring the audience list the
    Cognito HttpUserPoolAuthorizer this replaces used to synthesise into
    JwtConfiguration.Audience. An unset/empty smoke-test client is filtered
    out rather than treated as a wildcard match.
    """

    return [
        client_id
        for client_id in (
            os.getenv("UI_AUTH_USER_POOL_CLIENT_ID", ""),
            os.getenv("SMOKE_TEST_USER_POOL_CLIENT_ID", ""),
        )
        if client_id
    ]


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Return a payload-format-2.0 "simple" authorizer response.

    Fails closed: any unexpected exception while evaluating the token is
    caught and treated as unauthorized (``isAuthorized: False``) rather than
    left to propagate. API Gateway would otherwise turn an unhandled
    authorizer exception into a 500 -- but "deny the request" is the correct
    outcome for a bug in this Lambda, not "let it through unauthenticated"
    nor "surface a 500 to the caller instead of a clean 403".
    """

    try:
        token = _bearer_token(event)
        if not token:
            return {"isAuthorized": False}

        demo_claims = decode_demo_token(token)
        if demo_claims is not None:
            return {
                "isAuthorized": True,
                "context": {"authType": "demo", "demoOwner": demo_claims.owner},
            }

        if is_cognito_id_token(token, _cognito_client_ids()):
            return {"isAuthorized": True, "context": {"authType": "cognito"}}

        return {"isAuthorized": False}
    except Exception:  # deliberate fail-closed catch-all, see docstring above
        logger.exception("Gateway authorizer failed while evaluating bearer token")
        return {"isAuthorized": False}
