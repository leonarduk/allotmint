"""The signed-in user's saved chat conversation (#8870).

``GET/PUT/DELETE /chat/conversation`` and ``POST /chat/conversation/archive``,
plus the saved chats list: ``GET /chat/conversation/history``, and per chat
``PATCH`` (rename), ``DELETE`` and ``POST .../open`` under
``/chat/conversation/history/{chat_id}``.
Every handler is keyed by the authenticated user, so a caller can only reach
their own conversation; storage lives in :mod:`backend.common.chat_history`.

Demo sessions are read-only and share one identity across visitors, so they
read an empty conversation and are refused (403) every write.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError, model_validator

from backend.auth import get_current_user, is_demo_request
from backend.common import chat_history
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat/conversation", tags=["chat"])

# Limits on what one user may store; exceeding any of them is a 413.
MAX_DOCUMENT_BYTES = 1_000_000
MAX_NODES = 400
MAX_CONTENT_CHARS = 20_000

ROOT = "root"
CODE_CONFLICT = "chat_conversation_conflict"
CODE_UNAVAILABLE = "chat_history_unavailable"


class ChatNodeIn(BaseModel):
    id: str = Field(min_length=1, max_length=20)
    parentId: Optional[str] = Field(default=None, max_length=20)
    role: Literal["user", "assistant"]
    content: str


class ConversationIn(BaseModel):
    """The frontend's conversation tree (frontend/src/utils/chatConversation.ts)."""

    nodes: List[ChatNodeIn] = Field(default_factory=list)
    active: Dict[str, str] = Field(default_factory=dict)
    nextId: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _check_tree(self) -> "ConversationIn":
        parent_of: Dict[str, Optional[str]] = {}
        for node in self.nodes:
            if node.id in parent_of:
                raise ValueError(f"duplicate node id {node.id!r}")
            # Parents precede children, which also rules out cycles.
            if node.parentId is not None and node.parentId not in parent_of:
                raise ValueError(f"node {node.id!r} refers to a missing or later parent")
            parent_of[node.id] = node.parentId
        for key, child in self.active.items():
            if child not in parent_of or (parent_of[child] or ROOT) != key:
                raise ValueError(f"active entry {key!r} does not point at one of its children")
        return self


class ConversationPut(BaseModel):
    revision: int = Field(ge=0)
    conversation: ConversationIn


class RenameIn(BaseModel):
    """An empty title clears the name, so the chat is listed under its first question."""

    title: str = Field(max_length=1000)


def _check_limits(conversation: ConversationIn) -> None:
    if len(conversation.nodes) > MAX_NODES:
        raise HTTPException(status_code=413, detail=f"A saved chat can have at most {MAX_NODES} messages")
    if any(len(node.content) > MAX_CONTENT_CHARS for node in conversation.nodes):
        raise HTTPException(
            status_code=413, detail=f"A saved chat message can be at most {MAX_CONTENT_CHARS} characters"
        )


def _forbid_demo() -> None:
    if is_demo_request():
        raise HTTPException(status_code=403, detail="Demo sessions cannot save chat history")


def _unavailable(exc: chat_history.ChatHistoryUnavailable) -> JSONResponse:
    logger.warning("Chat history store unavailable: %s", sanitise_log_value(exc))
    return JSONResponse(
        status_code=503,
        content={"detail": "Chat history storage is unavailable", "code": CODE_UNAVAILABLE},
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="No saved chat with that id")


def _conflict(exc: chat_history.ChatConversationConflict) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": "The chat was changed in another tab or device",
            "code": CODE_CONFLICT,
            "current": exc.current,
        },
    )


async def _parse_put(request: Request) -> ConversationPut:
    # Refuse a declared oversize body before reading it into memory.
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Chat conversation is too large to save")
    body = await request.body()
    if len(body) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Chat conversation is too large to save")
    try:
        payload = ConversationPut.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False, include_context=False)) from exc
    _check_limits(payload.conversation)
    return payload


@router.get("")
def get_conversation(user: str = Depends(get_current_user)):
    """The saved conversation, plus ``owner``: an opaque id for the caller.

    The browser keeps ``owner`` with its local copy, so after a change of
    identity it can tell whose conversation it is holding and never uploads
    one user's cached chat into another user's account.
    """

    owner = chat_history.user_key(user)
    if is_demo_request():
        return {"owner": owner, "revision": 0, "conversation": chat_history.empty_conversation()}
    try:
        return {"owner": owner, **chat_history.load_conversation(user)}
    except chat_history.ChatHistoryUnavailable as exc:
        return _unavailable(exc)


@router.put("")
async def put_conversation(request: Request, user: str = Depends(get_current_user)):
    _forbid_demo()
    payload = await _parse_put(request)
    try:
        revision = chat_history.save_conversation(user, payload.conversation.model_dump(), payload.revision)
    except chat_history.ChatConversationConflict as exc:
        return _conflict(exc)
    except chat_history.ChatHistoryUnavailable as exc:
        return _unavailable(exc)
    return {"revision": revision}


@router.post("/archive")
def archive_conversation(user: str = Depends(get_current_user)):
    """Start a new chat, keeping the current one in the user's archive."""

    _forbid_demo()
    try:
        return chat_history.archive_conversation(user)
    except chat_history.ChatHistoryUnavailable as exc:
        return _unavailable(exc)


@router.delete("", status_code=204)
def delete_conversation(user: str = Depends(get_current_user)):
    """Delete the user's saved chat history: the current conversation and every archived one."""

    _forbid_demo()
    try:
        chat_history.delete_history(user)
    except chat_history.ChatHistoryUnavailable as exc:
        return _unavailable(exc)
    return Response(status_code=204)


@router.get("/history")
def list_history(user: str = Depends(get_current_user)):
    """The user's saved chats, newest first: the current one (``id`` ``current``) then the archived ones."""

    if is_demo_request():
        return {"chats": []}
    try:
        return {"chats": chat_history.list_conversations(user)}
    except chat_history.ChatHistoryUnavailable as exc:
        return _unavailable(exc)


@router.patch("/history/{chat_id}", status_code=204)
def rename_chat(chat_id: str, body: RenameIn, user: str = Depends(get_current_user)):
    _forbid_demo()
    try:
        chat_history.rename_conversation(user, chat_id, chat_history.clean_title(body.title))
    except chat_history.ChatConversationNotFound:
        raise _not_found() from None
    except chat_history.ChatHistoryUnavailable as exc:
        return _unavailable(exc)
    return Response(status_code=204)


@router.delete("/history/{chat_id}", status_code=204)
def delete_chat(chat_id: str, user: str = Depends(get_current_user)):
    """Delete one archived chat; the current one is put away with "New chat" (404 here)."""

    _forbid_demo()
    try:
        chat_history.delete_conversation(user, chat_id)
    except chat_history.ChatConversationNotFound:
        raise _not_found() from None
    except chat_history.ChatHistoryUnavailable as exc:
        return _unavailable(exc)
    return Response(status_code=204)


@router.post("/history/{chat_id}/open")
def open_chat(chat_id: str, user: str = Depends(get_current_user)):
    """Make an archived chat the current one; the current one is archived, as by "New chat"."""

    _forbid_demo()
    try:
        return chat_history.open_conversation(user, chat_id)
    except chat_history.ChatConversationNotFound:
        raise _not_found() from None
    except chat_history.ChatConversationConflict as exc:
        return _conflict(exc)
    except chat_history.ChatHistoryUnavailable as exc:
        return _unavailable(exc)
