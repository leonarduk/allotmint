"""POST /chat -- one turn of the tool-calling chat agent (Bedrock, Ollama or DeepSeek)."""

from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING, List, Literal, Optional

import httpx
import httpx2
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.chat.providers import run_configured_chat_turn
from backend.config import config
from backend.logging_setup import sanitise_log_value

if TYPE_CHECKING:
    from slowapi import Limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    # The client resends the full prior conversation each turn; nothing is
    # persisted server-side in this first pass (see docs/issue tracker for
    # the planned S3-backed history follow-up, mirroring backend/routes/
    # query.py's dual local/S3 persistence pattern).
    history: List[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str


def _find_upstream_error(exc: BaseException) -> Optional[BaseException]:
    """Return the first httpx/httpx2 error in ``exc``, unwrapping exception groups.

    The MCP SDK runs its transport in an anyio task group, so a refused
    connection to the MCP server arrives wrapped in an ``ExceptionGroup``.
    """

    if isinstance(exc, (httpx.HTTPError, httpx2.HTTPError)):
        return exc
    for inner in getattr(exc, "exceptions", ()):
        found = _find_upstream_error(inner)
        if found is not None:
            return found
    return None


def _upstream_error_detail(exc: BaseException) -> str:
    # httpx2 is only used by the MCP client (backend/chat/mcp_tools_client.py);
    # plain httpx only by the Ollama/DeepSeek loop (openai_compat_agent.py).
    if isinstance(exc, httpx2.HTTPError):
        return (
            f"Chat could not reach the MCP tools server ({type(exc).__name__}). "
            "Check it is running and that MCP_SERVER_URL points at it."
        )
    reason = type(exc).__name__
    if isinstance(exc, httpx.HTTPStatusError):
        reason = f"HTTP {exc.response.status_code}"
    return (
        f"Chat could not get a reply from the LLM provider ({reason}). "
        "Check it is running and that CHAT_PROVIDER / CHAT_MODEL / CHAT_BASE_URL are correct."
    )


async def _post_chat_impl(request: Request, payload: ChatRequest) -> ChatResponse:
    mcp_server_url = config.mcp_server_url
    if not mcp_server_url:
        raise HTTPException(status_code=503, detail="Chat is not configured (MCP_SERVER_URL unset)")

    try:
        reply = await run_configured_chat_turn(
            payload.message,
            [item.model_dump() for item in payload.history],
            cfg=config,
            mcp_server_url=mcp_server_url,
        )
    except ValueError as exc:
        # Raised by bedrock_agent._validate_message_alternation (shared by
        # both provider loops) for a
        # malformed history (e.g. two consecutive "user" messages) -- a
        # client bug, not a server error, so 400 rather than 500.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # A down MCP server or LLM is a misconfigured/unavailable upstream,
        # not a bug here: report which one as a 502 instead of a bare 500.
        upstream = _find_upstream_error(exc)
        if upstream is None:
            raise
        logger.warning("Chat upstream request failed: %s", sanitise_log_value(repr(upstream)))
        raise HTTPException(status_code=502, detail=_upstream_error_detail(upstream)) from exc
    return ChatResponse(reply=reply)


@router.post("/chat", response_model=ChatResponse)
async def post_chat(request: Request, payload: ChatRequest) -> ChatResponse:
    return await _post_chat_impl(request, payload)


def create_router(
    limiter: "Limiter | None" = None,
    rate_limit: str | None = None,
) -> APIRouter:
    """Return the chat router, optionally with per-IP rate limiting.

    Each request triggers a real Bedrock Converse call (plus MCP tool calls),
    so an unthrottled endpoint risks a client racking up AWS charges. Mirrors
    backend/routes/signup.py's create_router(limiter=..., rate_limit=...)
    pattern; the limiter must be the same instance registered on
    app.state.limiter so counters are shared across the application.

    If ``limiter`` is ``None`` (the default) or ``rate_limit`` is falsy, this
    returns the unprotected module-level ``router`` with no rate limiting --
    always pass both for a production mount.
    """

    if limiter is None or not rate_limit:
        warnings.warn(
            "create_router() returned the unprotected chat router with no "
            "rate limiting on POST /chat -- pass both limiter and rate_limit "
            "for a production mount.",
            RuntimeWarning,
            stacklevel=2,
        )
        return router

    limited = APIRouter(tags=["chat"])
    limited_post_chat = limiter.limit(rate_limit)(_post_chat_impl)
    limited.post("/chat", response_model=ChatResponse)(limited_post_chat)
    return limited
