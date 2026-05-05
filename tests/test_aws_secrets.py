"""Tests for backend.bootstrap.aws_secrets."""

import json
import os

import pytest

from backend.bootstrap.aws_secrets import load_aws_secrets_to_env


def test_no_op_outside_aws(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    # Should not call boto3 at all; no exception expected
    load_aws_secrets_to_env()
    assert os.getenv("JWT_SECRET") is None


def test_no_op_local_app_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    load_aws_secrets_to_env()
    assert os.getenv("JWT_SECRET") is None


@pytest.mark.parametrize("app_env", ["aws", "production"])
def test_injects_missing_env_vars(monkeypatch, app_env):
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)

    secret_payload = {
        "jwt_secret": "super-secret-key",
        "google_client_id": "client-id.apps.googleusercontent.com",
    }

    class _FakeClient:
        def get_secret_value(self, *, SecretId):
            return {"SecretString": json.dumps(secret_payload)}

    import boto3
    monkeypatch.setattr(boto3, "client", lambda *a, **kw: _FakeClient())

    load_aws_secrets_to_env(secret_name="test/secret")

    assert os.environ["JWT_SECRET"] == "super-secret-key"
    assert os.environ["GOOGLE_CLIENT_ID"] == "client-id.apps.googleusercontent.com"


def test_does_not_overwrite_existing_env_var(monkeypatch):
    monkeypatch.setenv("APP_ENV", "aws")
    monkeypatch.setenv("JWT_SECRET", "already-set")

    secret_payload = {"jwt_secret": "from-secrets-manager"}

    class _FakeClient:
        def get_secret_value(self, *, SecretId):
            return {"SecretString": json.dumps(secret_payload)}

    import boto3
    monkeypatch.setattr(boto3, "client", lambda *a, **kw: _FakeClient())

    load_aws_secrets_to_env(secret_name="test/secret")

    assert os.environ["JWT_SECRET"] == "already-set"


def test_boto3_error_does_not_raise(monkeypatch):
    monkeypatch.setenv("APP_ENV", "aws")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    class _FakeClient:
        def get_secret_value(self, *, SecretId):
            raise RuntimeError("network error")

    import boto3
    monkeypatch.setattr(boto3, "client", lambda *a, **kw: _FakeClient())

    # Must not propagate the exception
    load_aws_secrets_to_env(secret_name="test/secret")
    assert os.getenv("JWT_SECRET") is None


def test_invalid_json_does_not_raise(monkeypatch):
    monkeypatch.setenv("APP_ENV", "aws")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    class _FakeClient:
        def get_secret_value(self, *, SecretId):
            return {"SecretString": "not-json"}

    import boto3
    monkeypatch.setattr(boto3, "client", lambda *a, **kw: _FakeClient())

    load_aws_secrets_to_env(secret_name="test/secret")
    assert os.getenv("JWT_SECRET") is None


def test_missing_key_in_secret_is_skipped(monkeypatch):
    monkeypatch.setenv("APP_ENV", "aws")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    class _FakeClient:
        def get_secret_value(self, *, SecretId):
            return {"SecretString": json.dumps({"other_key": "value"})}

    import boto3
    monkeypatch.setattr(boto3, "client", lambda *a, **kw: _FakeClient())

    load_aws_secrets_to_env(secret_name="test/secret")
    assert os.getenv("JWT_SECRET") is None
