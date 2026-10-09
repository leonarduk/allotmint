"""Thin wrapper around the MCP Python SDK's streamable-HTTP client.

Connects to allotmint-pro's ``McpServerLambda`` Function URL, signing every
request with SigV4 (see ``sigv4_auth.py``) since that Function URL uses
``AWS_IAM`` auth. A server on localhost (``uvicorn
allotmint_pro.mcp_server.app:app``) is unauthenticated by design, so it is
called unsigned -- local development then needs no AWS credentials.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
from urllib.parse import urlparse

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from backend.chat.sigv4_auth import LambdaFunctionUrlSigV4Auth

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# The MCP SDK's own defaults (mcp.shared._httpx_utils): 30s connect/write/pool,
# 300s read so a response stream may stay open while a slow tool runs.
MCP_HTTP_TIMEOUT = httpx2.Timeout(30.0, read=300.0)


def _is_local_url(url: str) -> bool:
    return urlparse(url).hostname in _LOCAL_HOSTS


@asynccontextmanager
async def mcp_session(mcp_server_url: str) -> AsyncIterator[ClientSession]:
    """Open one MCP session for the duration of a single chat turn.

    The server runs in stateless-HTTP mode (see allotmint-pro's
    ``allotmint_pro/mcp_server/tools.py``), so there's no session state to
    reuse *across* chat turns -- but reusing one session for the several
    ``list_tools``/``call_tool`` calls made *within* one turn avoids
    reconnecting (and re-signing a fresh handshake) per call.
    """

    auth = None if _is_local_url(mcp_server_url) else LambdaFunctionUrlSigV4Auth()
    # mcp 2.x's streamable_http_client dropped the `auth` kwarg in favour of
    # accepting a pre-configured httpx2.AsyncClient (it builds its own default
    # client, without auth, when none is given) -- see #8131. That default
    # client carries the SDK's long read timeout; a bare httpx2.AsyncClient
    # would time out after 5s, cutting off slow tools (get_data_quality_report
    # takes ~100s) with "SSE stream ended without a response".
    async with httpx2.AsyncClient(auth=auth, timeout=MCP_HTTP_TIMEOUT) as http_client:
        async with streamable_http_client(mcp_server_url, http_client=http_client) as (
            read_stream,
            write_stream,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
