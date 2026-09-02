"""POST /chat -- one turn of the Bedrock tool-calling chat agent."""

from __future__ import annotations

import os
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.chat.bedrock_agent import run_chat_turn

router = APIRouter(tags=["chat"])


class ChatMessage(BaseModel):
    role: str
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


@router.post("/chat", response_model=ChatResponse)
async def post_chat(payload: ChatRequest) -> ChatResponse:
    mcp_server_url = os.getenv("MCP_SERVER_URL")
    if not mcp_server_url:
        raise HTTPException(status_code=503, detail="Chat is not configured (MCP_SERVER_URL unset)")
    bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

    reply = await run_chat_turn(
        payload.message,
        [item.model_dump() for item in payload.history],
        mcp_server_url=mcp_server_url,
        bedrock_model_id=bedrock_model_id,
    )
    return ChatResponse(reply=reply)
