"""Integration test: a minted demo token, end to end through the gateway
authorizer and a real protected route (#7524).

``tests/test_demo_authorizer_lambda.py`` covers the authorizer with
``decode_demo_token`` stubbed, and ``tests/test_demo_write_gate.py`` covers the
backend's demo-token handling on its own. This chains the two with no
stubbing of the token path: the same signed token and ``Authorization``
header go through ``backend.lambda_api.demo_authorizer.lambda_handler`` (as
API Gateway would call it, payload format 2.0) and then the real backend app
for ``GET /owners``. A token-format, header or owner-claim mismatch between
the two halves would fail here.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.app import create_app
from backend.config import config
from backend.lambda_api.demo_authorizer import lambda_handler

DEMO_OWNER = "demo"
OTHER_OWNER = "alice"
DEMO_LINK_INVALID_DETAIL = "Invalid authentication credentials"


def _authorizer_event(authorization: str) -> dict:
    """A payload-format-2.0 authorizer event for ``GET /owners``."""

    return {
        "version": "2.0",
        "type": "REQUEST",
        "routeArn": "arn:aws:execute-api:eu-west-2:123456789012:api-id/$default/GET/owners",
        "identitySource": [authorization],
        "routeKey": "ANY /{proxy+}",
        "rawPath": "/owners",
        "rawQueryString": "",
        "headers": {"authorization": authorization},
        "requestContext": {"http": {"method": "GET", "path": "/owners"}},
    }


def _tampered(token: str) -> str:
    """``token`` with its owner claim swapped but the original signature kept."""

    header, _payload, signature = token.split(".")
    forged = jwt.encode(
        {"scope": auth.DEMO_SCOPE, "owner": "steve", "exp": 4102444800},
        "not-the-real-secret-but-32-bytes-long",
        algorithm=auth.ALGORITHM,
    )
    return ".".join([header, forged.split(".")[1], signature])


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    # No Cognito audiences: the authorizer must admit the token as a demo
    # token, never fall back to (networked) Cognito verification.
    monkeypatch.delenv("UI_AUTH_USER_POOL_CLIENT_ID", raising=False)
    monkeypatch.delenv("SMOKE_TEST_USER_POOL_CLIENT_ID", raising=False)
    monkeypatch.setenv("TESTING", "1")
    app = create_app()
    # Patched after create_app(), whose config reload would otherwise
    # overwrite it -- see test_demo_write_gate.py.
    monkeypatch.setattr(config, "demo_link_enabled", True, raising=False)
    monkeypatch.setattr(config, "demo_link_owner", DEMO_OWNER, raising=False)
    # Two owners on disk, so "only the demo owner" proves scoping rather than
    # reflecting a data set that happens to hold just one.
    for owner in (DEMO_OWNER, OTHER_OWNER):
        owner_dir = tmp_path / owner
        owner_dir.mkdir()
        (owner_dir / "person.json").write_text(json.dumps({"full_name": owner}), encoding="utf-8")
        (owner_dir / "isa.json").write_text(json.dumps({"account_type": "isa", "holdings": []}), encoding="utf-8")
    with TestClient(app) as test_client:
        app.state.accounts_root = tmp_path
        yield test_client


def test_demo_token_is_authorized_and_reads_only_the_demo_owner(client: TestClient) -> None:
    unscoped = {summary["owner"] for summary in client.get("/owners").json()}
    assert {DEMO_OWNER, OTHER_OWNER} <= unscoped

    authorization = f"Bearer {auth.create_demo_access_token(DEMO_OWNER)}"

    decision = lambda_handler(_authorizer_event(authorization), None)

    assert decision == {"isAuthorized": True, "context": {"authType": "demo", "demoOwner": DEMO_OWNER}}

    response = client.get("/owners", headers={"Authorization": authorization})

    assert response.status_code == 200
    owners = [summary["owner"] for summary in response.json()]
    assert owners == [DEMO_OWNER]


@pytest.mark.parametrize(
    "token_factory",
    [
        pytest.param(
            lambda: auth.create_demo_access_token(DEMO_OWNER, expires_delta=timedelta(seconds=-1)),
            id="expired",
        ),
        pytest.param(lambda: _tampered(auth.create_demo_access_token(DEMO_OWNER)), id="tampered"),
    ],
)
def test_invalid_demo_token_is_denied_by_authorizer(token_factory) -> None:
    """An expired or tampered token never reaches the backend: the gateway
    denies it. The backend does not re-verify it -- like the deployed Lambda,
    the test app runs with ``disable_auth`` on, so a token that is not a valid
    demo token falls through to the normal path -- which is why the
    authorizer's denial is the assertion that matters here."""

    authorization = f"Bearer {token_factory()}"

    assert lambda_handler(_authorizer_event(authorization), None) == {"isAuthorized": False}


def test_demo_token_for_another_owner_passes_authorizer_but_backend_rejects(client: TestClient) -> None:
    """The authorizer checks structure only; the backend enforces the
    configured demo owner (see demo_authorizer's module docstring). A
    correctly signed demo token for a different owner must still be
    rejected by the backend."""

    authorization = f"Bearer {auth.create_demo_access_token('steve')}"

    decision = lambda_handler(_authorizer_event(authorization), None)
    assert decision == {"isAuthorized": True, "context": {"authType": "demo", "demoOwner": "steve"}}

    response = client.get("/owners", headers={"Authorization": authorization})

    assert response.status_code == 401
    assert response.json()["detail"] == DEMO_LINK_INVALID_DETAIL
