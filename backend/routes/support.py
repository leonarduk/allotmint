import asyncio
import os
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.utils.telegram_utils import send_message
from scripts.check_portfolio_health import run_check

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


class PortfolioHealthRequest(BaseModel):
    threshold: float | None = None


@router.post("/portfolio-health")
async def post_portfolio_health(req: PortfolioHealthRequest | None = None) -> dict[str, Any]:
    """Run portfolio health check and return structured findings."""

    threshold = (
        req.threshold
        if req and req.threshold is not None
        else float(os.getenv("DRAWDOWN_THRESHOLD", "0.2"))
    )

    try:
        findings = await asyncio.to_thread(run_check, threshold)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="health check failed") from exc

    for f in findings:
        msg = f.get("message", "")
        m = re.search(r"Instrument metadata (.+) not found", msg)
        if m:
            path = m.group(1)
            f["suggestion"] = f"Create {path} with instrument details."
            continue
        m = re.search(r"approvals file for '([^']+)' not found", msg)
        if m:
            owner = m.group(1)
            f["suggestion"] = f"Add approvals.json under accounts/{owner}/."

    return {"status": "ok", "findings": findings}
