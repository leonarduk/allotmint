"""POST /chat -- one turn of the Bedrock tool-calling chat agent."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, List, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.chat.bedrock_agent import run_chat_turn
from backend.config import config

if TYPE_CHECKING:
    from slowapi import Limiter

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


async def _post_chat_impl(request: Request, payload: ChatRequest) -> ChatResponse:
    mcp_server_url = config.mcp_server_url
    if not mcp_server_url:
        raise HTTPException(status_code=503, detail="Chat is not configured (MCP_SERVER_URL unset)")

    reply = await run_chat_turn(
        payload.message,
        [item.model_dump() for item in payload.history],
        mcp_server_url=mcp_server_url,
        bedrock_model_id=config.bedrock_model_id,
    )
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
