from unittest.mock import MagicMock, patch

import httpx2
import pytest
from botocore.credentials import Credentials

from backend.chat.sigv4_auth import LambdaFunctionUrlSigV4Auth


def _make_auth(region="eu-west-1"):
    fake_session = MagicMock()
    fake_session.get_credentials.return_value = Credentials("AKIAFAKE", "secretfake")
    fake_session.region_name = region
    with patch("backend.chat.sigv4_auth.boto3.Session", return_value=fake_session):
        return LambdaFunctionUrlSigV4Auth()


def test_init_raises_without_credentials():
    fake_session = MagicMock()
    fake_session.get_credentials.return_value = None
    fake_session.region_name = "eu-west-1"
    with patch("backend.chat.sigv4_auth.boto3.Session", return_value=fake_session):
        with pytest.raises(RuntimeError, match="No AWS credentials"):
            LambdaFunctionUrlSigV4Auth()


def test_init_raises_without_region():
    fake_session = MagicMock()
    fake_session.get_credentials.return_value = Credentials("AKIAFAKE", "secretfake")
    fake_session.region_name = None
    with patch("backend.chat.sigv4_auth.boto3.Session", return_value=fake_session):
        with pytest.raises(RuntimeError, match="No AWS region"):
            LambdaFunctionUrlSigV4Auth(region=None)


def test_init_explicit_region_overrides_session_region():
    fake_session = MagicMock()
    fake_session.get_credentials.return_value = Credentials("AKIAFAKE", "secretfake")
    fake_session.region_name = "us-east-1"
    with patch("backend.chat.sigv4_auth.boto3.Session", return_value=fake_session):
        auth = LambdaFunctionUrlSigV4Auth(region="eu-west-1")
    assert auth._region == "eu-west-1"


def test_auth_flow_signs_request_as_lambda_service():
    # Confirms the auth_flow generator adds SigV4 headers (Authorization,
    # X-Amz-Date) signed for the "lambda" service -- not "execute-api" --
    # per the class's own documented rationale. Also confirms it works
    # against an httpx2.Request (the SDK's client class after the mcp 2.x /
    # httpx2 migration, #8131) rather than the old httpx.Request.
    auth = _make_auth()
    request = httpx2.Request(
        "POST",
        "https://abc123.lambda-url.eu-west-1.on.aws/mcp",
        content=b'{"jsonrpc": "2.0"}',
        headers={"content-type": "application/json"},
    )

    flow = auth.auth_flow(request)
    signed_request = next(flow)

    assert signed_request is request
    assert "authorization" in signed_request.headers
    assert "Credential=AKIAFAKE" in signed_request.headers["authorization"]
    assert "/lambda/aws4_request" in signed_request.headers["authorization"]
    assert "x-amz-date" in signed_request.headers

    with pytest.raises(StopIteration):
        flow.send(httpx2.Response(200, request=request))


def test_auth_flow_preserves_existing_headers():
    auth = _make_auth()
    request = httpx2.Request(
        "GET",
        "https://abc123.lambda-url.eu-west-1.on.aws/mcp",
        headers={"content-type": "application/json"},
    )
    signed_request = next(auth.auth_flow(request))
    assert signed_request.headers["content-type"] == "application/json"
