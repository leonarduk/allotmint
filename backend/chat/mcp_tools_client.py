"""Thin wrapper around the MCP Python SDK's streamable-HTTP client.

Connects to allotmint-pro's ``McpServerLambda`` Function URL, signing every
request with SigV4 (see ``sigv4_auth.py``) since that Function URL uses
``AWS_IAM`` auth.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from backend.chat.sigv4_auth import LambdaFunctionUrlSigV4Auth


@asynccontextmanager
async def mcp_session(mcp_server_url: str) -> AsyncIterator[ClientSession]:
    """Open one MCP session for the duration of a single chat turn.

    The server runs in stateless-HTTP mode (see allotmint-pro's
    ``allotmint_pro/mcp_server/tools.py``), so there's no session state to
    reuse *across* chat turns -- but reusing one session for the several
    ``list_tools``/``call_tool`` calls made *within* one turn avoids
    reconnecting (and re-signing a fresh handshake) per call.
    """

    auth = LambdaFunctionUrlSigV4Auth()
    async with streamablehttp_client(mcp_server_url, auth=auth) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session
