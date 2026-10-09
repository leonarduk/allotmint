"""Trend-watch routes (#10476): the latest review list, an on-demand run, and the mute list."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.auth import get_active_user
from backend.common.authz import ensure_owner_access
from backend.common.portfolio import build_owner_portfolio
from backend.routes._accounts import resolve_accounts_root
from backend.trend_watch import storage
from backend.trend_watch.service import run_for_owner
from backend.trend_watch.settings import load_trend_watch_config

router = APIRouter(prefix="/trend-watch", tags=["trend-watch"])


class MuteRequest(BaseModel):
    muted: bool


class TrendWatchSettings(BaseModel):
    """Public detector thresholds, shown beside the review list."""

    min_signals: int
    min_new_signals: int
    new_lookback_days: int
    memory_runs: int
    sma_slope_days: int
    rs_low_days: int
    swing_days: int
    market_move_tolerance: float
    max_investigated: int
    max_tool_calls: int


def _authorise(owner: str, request: Request, identity: str | None) -> str:
    """Validate ``owner`` and check access; return the cleaned owner every later call uses."""

    try:
        cleaned = storage.clean_owner(owner)
    except storage.InvalidOwner as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ensure_owner_access(identity, cleaned, resolve_accounts_root(request, allow_missing=True))
    return cleaned


@router.get("/settings", response_model=TrendWatchSettings)
def settings() -> TrendWatchSettings:
    return TrendWatchSettings.model_validate(load_trend_watch_config(), from_attributes=True)


@router.get("/{owner}/latest")
def latest(owner: str, request: Request, identity: str | None = Depends(get_active_user)) -> Dict[str, Any]:
    """The most recent stored report for ``owner``; 404 before the first run."""

    owner = _authorise(owner, request, identity)
    report = storage.load_latest(owner)
    if report is None:
        raise HTTPException(status_code=404, detail="No trend-watch report yet; run one first.")
    report["mutes"] = storage.load_mutes(owner)
    return report


@router.post("/{owner}/run")
async def run(
    owner: str, request: Request, notify: bool = False, identity: str | None = Depends(get_active_user)
) -> Dict[str, Any]:
    """Run trend watch for ``owner`` now, store the report and return it."""

    owner = _authorise(owner, request, identity)
    accounts_root = resolve_accounts_root(request, allow_missing=True)
    try:
        return await run_for_owner(
            owner, notify=notify, load_portfolio=lambda name: build_owner_portfolio(name, accounts_root)
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Owner not found") from exc


@router.put("/{owner}/mutes/{ticker}")
def set_mute(
    owner: str, ticker: str, body: MuteRequest, request: Request, identity: str | None = Depends(get_active_user)
) -> Dict[str, List[str]]:
    """Mark ``ticker`` as a deliberate long-term or residual holding (shown with less emphasis), or undo it."""

    owner = _authorise(owner, request, identity)
    try:
        return {"mutes": storage.set_muted(owner, ticker, body.muted)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
