from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.chat import mcp_tools_client


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://localhost:8001/mcp", True),
        ("http://127.0.0.1:8001/mcp", True),
        ("http://[::1]:8001/mcp", True),
        ("https://abc123.lambda-url.eu-west-1.on.aws/mcp", False),
        ("https://localhost.example.com/mcp", False),
    ],
)
def test_is_local_url(url, expected):
    assert mcp_tools_client._is_local_url(url) is expected


def test_mcp_http_timeout_allows_slow_tools():
    # httpx2's 5s default read timeout cut get_data_quality_report (~100s) off
    # mid-stream with "SSE stream ended without a response" (#10471).
    assert mcp_tools_client.MCP_HTTP_TIMEOUT.read == 300.0
    assert mcp_tools_client.MCP_HTTP_TIMEOUT.connect == 30.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "expect_auth"),
    [
        ("http://localhost:8001/mcp", False),
        ("https://abc123.lambda-url.eu-west-1.on.aws/mcp", True),
    ],
)
async def test_mcp_session_wires_auth_into_httpx2_client(url, expect_auth):
    # Pins the mcp 2.x / httpx2 migration (#8131): auth must be passed via a
    # pre-configured httpx2.AsyncClient (the `http_client` kwarg), not the
    # old streamablehttp_client(..., auth=...) shape, and only for
    # non-local URLs.
    fake_auth_instance = MagicMock(name="LambdaFunctionUrlSigV4Auth instance")
    fake_read_stream = MagicMock(name="read_stream")
    fake_write_stream = MagicMock(name="write_stream")
    fake_session = AsyncMock()

    @asynccontextmanager
    async def fake_streamable_http_client(mcp_server_url, *, http_client):
        assert mcp_server_url == url
        assert http_client is fake_http_client
        yield (fake_read_stream, fake_write_stream)

    fake_http_client = AsyncMock()
    fake_http_client.__aenter__.return_value = fake_http_client

    with (
        patch(
            "backend.chat.mcp_tools_client.LambdaFunctionUrlSigV4Auth",
            return_value=fake_auth_instance,
        ) as mock_auth_cls,
        patch(
            "backend.chat.mcp_tools_client.httpx2.AsyncClient",
            return_value=fake_http_client,
        ) as mock_async_client_cls,
        patch(
            "backend.chat.mcp_tools_client.streamable_http_client",
            side_effect=fake_streamable_http_client,
        ),
        patch(
            "backend.chat.mcp_tools_client.ClientSession",
            return_value=fake_session,
        ),
    ):
        fake_session.__aenter__.return_value = fake_session
        async with mcp_tools_client.mcp_session(url) as session:
            assert session is fake_session

    mock_async_client_cls.assert_called_once_with(
        auth=fake_auth_instance if expect_auth else None,
        timeout=mcp_tools_client.MCP_HTTP_TIMEOUT,
    )
    assert mock_auth_cls.called is expect_auth
    fake_session.initialize.assert_awaited_once()
