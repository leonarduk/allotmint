"""Routes for timestamped instrument research notes (see :mod:`backend.instrument_notes`)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, NoReturn, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend import instrument_notes as notes
from backend.auth import get_active_user
from backend.routes.alert_settings import _resolve_identity, _validate_owner

router = APIRouter(prefix="/instrument-notes", tags=["research"])


class NoteCreate(BaseModel):
    ticker: str
    stance: Literal["bullish", "bearish", "neutral"]
    text: str = Field(min_length=1, max_length=notes.MAX_NOTE_LENGTH)
    price: Optional[float] = Field(default=None, gt=0)


async def _identity(user: str, request: Request, current_user: str | None) -> str:
    identity = await _resolve_identity(request, current_user)
    _validate_owner(user, identity)
    return identity


def _raise(exc: notes.NoteError) -> NoReturn:
    missing = isinstance(exc, notes.NoteNotFound)
    code = status.HTTP_404_NOT_FOUND if missing else status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("/{user}")
async def list_notes(
    user: str,
    request: Request,
    ticker: Optional[str] = None,
    current_user: str | None = Depends(get_active_user),
) -> List[Dict[str, Any]]:
    """Return ``user``'s notes, newest first, optionally for one ticker."""
    return notes.list_notes(await _identity(user, request, current_user), ticker=ticker)


@router.post("/{user}", status_code=status.HTTP_201_CREATED)
async def create_note(
    user: str,
    payload: NoteCreate,
    request: Request,
    current_user: str | None = Depends(get_active_user),
) -> Dict[str, Any]:
    identity = await _identity(user, request, current_user)
    try:
        return notes.create_note(identity, **payload.model_dump())
    except notes.NoteError as exc:
        _raise(exc)


@router.delete("/{user}/{note_id}")
async def delete_note(
    user: str,
    note_id: str,
    request: Request,
    current_user: str | None = Depends(get_active_user),
) -> Dict[str, Any]:
    identity = await _identity(user, request, current_user)
    try:
        return {"status": "deleted", "note": notes.delete_note(identity, note_id)}
    except notes.NoteError as exc:
        _raise(exc)
