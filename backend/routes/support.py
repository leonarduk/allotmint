from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
import re
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.utils.telegram_utils import send_message
from scripts.check_portfolio_health import run_check

router = APIRouter(prefix="/support", tags=["support"])

logger = logging.getLogger(__name__)


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


@dataclass
class _PortfolioHealthSnapshot:
    threshold: float
    findings: list[dict[str, Any]]
    generated_at: datetime


_portfolio_health_cache: Optional[_PortfolioHealthSnapshot] = None
_portfolio_health_refresh: Optional[tuple[float, asyncio.Task[_PortfolioHealthSnapshot]]] = None
_portfolio_health_ttl = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cache_is_fresh(cache: _PortfolioHealthSnapshot, threshold: float) -> bool:
    if cache.threshold != threshold:
        return False
    return _now() - cache.generated_at <= _portfolio_health_ttl


async def _compute_portfolio_health(threshold: float) -> _PortfolioHealthSnapshot:
    findings = await asyncio.to_thread(run_check, threshold)
    return _PortfolioHealthSnapshot(
        threshold=threshold,
        findings=findings,
        generated_at=_now(),
    )


async def _refresh_portfolio_health(threshold: float) -> _PortfolioHealthSnapshot:
    current_task = asyncio.current_task()
    snapshot = await _compute_portfolio_health(threshold)
    global _portfolio_health_cache, _portfolio_health_refresh
    _portfolio_health_cache = snapshot
    if current_task is not None and _portfolio_health_refresh is not None:
        cached_threshold, task = _portfolio_health_refresh
        if cached_threshold == threshold and task is current_task:
            _portfolio_health_refresh = None
    return snapshot


def _ensure_refresh_task(threshold: float) -> asyncio.Task[_PortfolioHealthSnapshot]:
    global _portfolio_health_refresh
    if _portfolio_health_refresh is not None:
        cached_threshold, task = _portfolio_health_refresh
        if cached_threshold == threshold and not task.done():
            return task
    task = asyncio.create_task(_refresh_portfolio_health(threshold))
    task.add_done_callback(_log_refresh_failure)
    _portfolio_health_refresh = (threshold, task)
    return task


def _log_refresh_failure(task: asyncio.Task[_PortfolioHealthSnapshot]) -> None:
    try:
        task.result()
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Portfolio health refresh failed: %s", exc)


def _format_portfolio_health_response(
    snapshot: _PortfolioHealthSnapshot,
    *,
    stale: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "ok",
        "findings": snapshot.findings,
        "generated_at": snapshot.generated_at.isoformat(),
    }
    if stale:
        payload["stale"] = True
    return payload


@router.post("/portfolio-health")
async def post_portfolio_health(req: PortfolioHealthRequest | None = None) -> dict[str, Any]:
    """Run portfolio health check and return structured findings."""

    threshold = (
        req.threshold
        if req and req.threshold is not None
        else float(os.getenv("DRAWDOWN_THRESHOLD", "0.2"))
    )

    global _portfolio_health_cache
    cache = _portfolio_health_cache
    stale = False

    if cache and _cache_is_fresh(cache, threshold):
        snapshot = cache
    else:
        if cache and cache.threshold == threshold:
            task = _ensure_refresh_task(threshold)
            if task.done():
                try:
                    snapshot = task.result()
                except Exception as exc:  # pragma: no cover - defensive
                    raise HTTPException(status_code=500, detail="health check failed") from exc
            else:
                snapshot = cache
                stale = True
        else:
            task = _ensure_refresh_task(threshold)
            try:
                snapshot = await task
            except Exception as exc:  # pragma: no cover - defensive
                raise HTTPException(status_code=500, detail="health check failed") from exc
        if cache is None or cache.threshold != threshold:
            stale = False

    response = _format_portfolio_health_response(snapshot, stale=stale)

    for f in response["findings"]:
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

    return response
