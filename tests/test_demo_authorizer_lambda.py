"""Tests for the API Gateway Lambda authorizer (backend/lambda_api/demo_authorizer.py, #7522).

Covers the "accept Cognito OR demo token" contract, the payload-format-2.0
simple-response shape, and the fail-closed behaviour on an unexpected error.
"""

from __future__ import annotations

import backend.lambda_api.demo_authorizer as mod
from backend.auth import DemoTokenClaims


def _event(token: str | None, *, via_headers: bool = False) -> dict:
    if token is None:
        return {"headers": {}, "identitySource": []}
    header_value = f"Bearer {token}"
    if via_headers:
        return {"headers": {"authorization": header_value}, "identitySource": []}
    return {"headers": {}, "identitySource": [header_value]}


def test_bearer_token_extracted_from_identity_source():
    assert mod._bearer_token(_event("abc")) == "abc"


def test_bearer_token_falls_back_to_headers():
    assert mod._bearer_token(_event("abc", via_headers=True)) == "abc"


def test_bearer_token_missing_returns_none():
    assert mod._bearer_token(_event(None)) is None


def test_bearer_token_without_bearer_prefix_returned_as_is():
    assert mod._bearer_token({"headers": {}, "identitySource": ["raw-token"]}) == "raw-token"


def test_cognito_client_ids_filters_blank_smoke_test_client(monkeypatch):
    monkeypatch.setenv("UI_AUTH_USER_POOL_CLIENT_ID", "ui-client")
    monkeypatch.setenv("SMOKE_TEST_USER_POOL_CLIENT_ID", "")
    assert mod._cognito_client_ids() == ["ui-client"]


def test_cognito_client_ids_includes_smoke_test_client_when_set(monkeypatch):
    monkeypatch.setenv("UI_AUTH_USER_POOL_CLIENT_ID", "ui-client")
    monkeypatch.setenv("SMOKE_TEST_USER_POOL_CLIENT_ID", "smoke-client")
    assert mod._cognito_client_ids() == ["ui-client", "smoke-client"]


def test_lambda_handler_admits_valid_demo_token(monkeypatch):
    monkeypatch.setattr(mod, "decode_demo_token", lambda token: DemoTokenClaims(owner="demo", scope="demo-readonly"))
    monkeypatch.setattr(mod, "is_cognito_id_token", lambda token, client_ids: False)

    result = mod.lambda_handler(_event("demo-token"), {})

    assert result == {"isAuthorized": True, "context": {"authType": "demo", "demoOwner": "demo"}}


def test_lambda_handler_admits_valid_cognito_token(monkeypatch):
    monkeypatch.setattr(mod, "decode_demo_token", lambda token: None)
    monkeypatch.setattr(mod, "is_cognito_id_token", lambda token, client_ids: True)

    result = mod.lambda_handler(_event("cognito-token"), {})

    assert result == {"isAuthorized": True, "context": {"authType": "cognito"}}


def test_lambda_handler_rejects_token_that_is_neither(monkeypatch, caplog):
    monkeypatch.setattr(mod, "decode_demo_token", lambda token: None)
    monkeypatch.setattr(mod, "is_cognito_id_token", lambda token, client_ids: False)

    with caplog.at_level("INFO", logger=mod.logger.name):
        result = mod.lambda_handler(_event("garbage"), {})

    assert result == {"isAuthorized": False}
    # A denial must always leave a trace in this Lambda's own logs (see the
    # module docstring): a prior incident had no log line at all here for an
    # ordinary "token doesn't validate" denial, which made a systemic
    # JWT_SECRET mismatch indistinguishable from a client sending garbage.
    assert "neither a valid demo token nor a valid Cognito ID token" in caplog.text
    assert "garbage" not in caplog.text


def test_lambda_handler_rejects_missing_bearer_token(monkeypatch, caplog):
    called = []
    monkeypatch.setattr(mod, "decode_demo_token", lambda token: called.append(token))
    monkeypatch.setattr(mod, "is_cognito_id_token", lambda token, client_ids: called.append(token))

    with caplog.at_level("INFO", logger=mod.logger.name):
        result = mod.lambda_handler(_event(None), {})

    assert result == {"isAuthorized": False}
    assert called == []
    assert "no bearer token present" in caplog.text


def test_lambda_handler_fails_closed_on_unexpected_exception(monkeypatch):
    def _boom(token):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "decode_demo_token", _boom)

    result = mod.lambda_handler(_event("anything"), {})

    assert result == {"isAuthorized": False}
