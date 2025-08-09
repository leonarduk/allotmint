from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.utils.telegram_utils import send_message

router = APIRouter(prefix="/support", tags=["support"])


class TelegramRequest(BaseModel):
    text: str


@router.post("/telegram")
async def post_telegram(msg: TelegramRequest) -> dict[str, str]:
    """Forward ``msg.text`` to the configured Telegram chat."""

    try:
        send_message(msg.text)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="failed to send message") from exc
    return {"status": "ok"}
