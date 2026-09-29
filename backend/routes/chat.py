"""POST /chat -- one turn of the tool-calling chat agent (Bedrock, Ollama or DeepSeek)."""

from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING, List, Literal, Optional

import httpx
import httpx2
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.chat.local_tools import LocalTools, pages_from_request
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


class ChatPageIn(BaseModel):
    # Same-site paths only: a leading "//" would be a protocol-relative URL.
    path: str = Field(pattern=r"^/([^/].*)?$", max_length=200)
    label: str = Field(min_length=1, max_length=100)


class ChatRequest(BaseModel):
    message: str
    # The client resends the full prior conversation each turn; nothing is
    # persisted server-side in this first pass (see docs/issue tracker for
    # the planned S3-backed history follow-up, mirroring backend/routes/
    # query.py's dual local/S3 persistence pattern).
    history: List[ChatMessage] = Field(default_factory=list)
    # Pages the client can open. When present the model gets a
    # navigate_to_page tool limited to these paths (backend/chat/local_tools.py).
    pages: List[ChatPageIn] = Field(default_factory=list, max_length=100)


class ChatResponse(BaseModel):
    reply: str
    # Set when the model asked to open a page; always one of the request's pages.
    navigate_to: Optional[str] = None


# Stable, machine-readable failure codes sent alongside `detail`, so the
# frontend can name the failing piece with its own fixed wording (#7721)
# instead of echoing backend text or collapsing every 502 into one message.
CHAT_ERROR_NOT_CONFIGURED = "chat_not_configured"
CHAT_ERROR_MCP_UNREACHABLE = "mcp_unreachable"
CHAT_ERROR_LLM_UNREACHABLE = "llm_unreachable"
CHAT_ERROR_AWS = "aws_error"

_UPSTREAM_ERRORS = (httpx.HTTPError, httpx2.HTTPError, BotoCoreError, ClientError)


def _find_upstream_error(exc: BaseException) -> Optional[BaseException]:
    """Return the first upstream (HTTP/AWS) error in ``exc``, unwrapping groups and causes.

    The MCP SDK runs its transport in an anyio task group, so a refused
    connection to the MCP server arrives wrapped in an ``ExceptionGroup``.
    """

    if isinstance(exc, _UPSTREAM_ERRORS):
        return exc
    for inner in (*getattr(exc, "exceptions", ()), exc.__cause__):
        found = _find_upstream_error(inner) if inner is not None else None
        if found is not None:
            return found
    return None


def _chat_error(status_code: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail, "code": code})


def _describe_upstream_error(exc: BaseException) -> tuple[str, str]:
    """Return the ``(code, detail)`` for an upstream error found by ``_find_upstream_error``."""
    # httpx2 is only used by the MCP client (backend/chat/mcp_tools_client.py);
    # plain httpx only by the Ollama/DeepSeek loop (openai_compat_agent.py);
    # botocore by Bedrock (bedrock_agent.py) and MCP request signing (sigv4_auth.py),
    # which can't be told apart by type, so aws_error names neither as the culprit.
    if isinstance(exc, httpx2.HTTPError):
        return CHAT_ERROR_MCP_UNREACHABLE, (
            f"Chat could not reach the MCP tools server ({type(exc).__name__}). "
            "Check it is running and that MCP_SERVER_URL points at it."
        )
    if isinstance(exc, (BotoCoreError, ClientError)):
        reason = type(exc).__name__
        if isinstance(exc, ClientError):
            reason = exc.response.get("Error", {}).get("Code", reason)
        return CHAT_ERROR_AWS, (
            f"Chat's AWS call failed ({reason}), from Bedrock or from signing MCP requests. "
            "Check the AWS credentials and region, and Bedrock model access for BEDROCK_MODEL_ID."
        )
    reason = type(exc).__name__
    if isinstance(exc, httpx.HTTPStatusError):
        reason = f"HTTP {exc.response.status_code}"
    return CHAT_ERROR_LLM_UNREACHABLE, (
        f"Chat could not get a reply from the LLM provider ({reason}). "
        "Check it is running and that CHAT_PROVIDER / CHAT_MODEL / CHAT_BASE_URL are correct."
    )


async def _post_chat_impl(request: Request, payload: ChatRequest) -> ChatResponse | JSONResponse:
    mcp_server_url = config.mcp_server_url
    if not mcp_server_url:
        return _chat_error(503, CHAT_ERROR_NOT_CONFIGURED, "Chat is not configured (MCP_SERVER_URL unset)")

    local_tools = LocalTools(pages=pages_from_request([page.model_dump() for page in payload.pages]))
    try:
        reply = await run_configured_chat_turn(
            payload.message,
            [item.model_dump() for item in payload.history],
            cfg=config,
            mcp_server_url=mcp_server_url,
            local_tools=local_tools,
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
        return _chat_error(502, *_describe_upstream_error(upstream))
    return ChatResponse(reply=reply, navigate_to=local_tools.navigate_to)


@router.post("/chat", response_model=ChatResponse)
async def post_chat(request: Request, payload: ChatRequest) -> ChatResponse | JSONResponse:
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
