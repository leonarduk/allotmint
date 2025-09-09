from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend import nudges as nudge_utils
from backend.common import data_loader
from backend.common.errors import OWNER_NOT_FOUND

router = APIRouter(prefix="/nudges", tags=["nudges"])


def _validate_owner(user: str, request: Request) -> None:
    owners = {o["owner"] for o in data_loader.list_plots(request.app.state.accounts_root)}
    if user not in owners:
        raise HTTPException(status_code=404, detail=OWNER_NOT_FOUND)


class SubscribePayload(BaseModel):
    user: str
    frequency: int
    snooze_until: Optional[str] = None


@router.post("/subscribe")
async def subscribe(payload: SubscribePayload, request: Request):
    _validate_owner(payload.user, request)
    nudge_utils.set_user_nudge(payload.user, payload.frequency, payload.snooze_until)
    return {"status": "ok"}


class SnoozePayload(BaseModel):
    user: str
    days: int = 1


@router.post("/snooze")
async def snooze(payload: SnoozePayload, request: Request):
    _validate_owner(payload.user, request)
    nudge_utils.snooze_user(payload.user, payload.days)
    return {"status": "ok"}


@router.get("/")
async def list_nudges():
    return nudge_utils.get_recent_nudges()
