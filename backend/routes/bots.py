"""Bots page API: list automated jobs/agents, their runs, Run now and settings (#10477).

Viewing follows owner access: system-scoped runs are visible to any signed-in
user, owner-scoped runs only to callers who can access that owner. Run now
and settings changes need admin -- the same configured-owner-email gate as
the MCP server and app-update routes -- and are never available to a demo
token (on AWS ``disable_auth`` is true, so the demo check matters there).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ValidationError

from backend.auth import is_demo_request
from backend.bots import runner
from backend.bots.registry import Bot, BotKind, BotScope, get_bot, list_bots
from backend.bots.runs import MAX_RUNS, RunRecord, get_run, list_runs
from backend.bots.settings import load_settings, save_settings
from backend.common.authz import ensure_owner_access
from backend.common.errors import PermissionDeniedError
from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.routes import get_active_user
from backend.routes.mcp_server_admin import _ensure_admin_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bots", tags=["bots"])

_FORBIDDEN_DETAIL = "Not authorized to manage bots"


class BotSummary(BaseModel):
    id: str
    name: str
    description: str
    kind: BotKind
    scope: BotScope
    enabled: bool
    cadence: str
    schedule: Optional[str] = None
    next_run: Optional[datetime] = None
    running: bool = False
    last_run: Optional[RunRecord] = None


class BotDetail(BotSummary):
    settings: Dict[str, Any]
    settings_schema: Dict[str, Any]
    can_manage: bool = False


def _is_admin(identity: Optional[str]) -> bool:
    if is_demo_request():
        return False
    try:
        _ensure_admin_access(identity)
    except HTTPException:
        return False
    return True


def _require_admin(identity: Optional[str] = Depends(get_active_user)) -> Optional[str]:
    if not _is_admin(identity):
        raise HTTPException(status_code=403, detail=_FORBIDDEN_DETAIL)
    return identity


def _bot_or_404(bot_id: str) -> Bot:
    try:
        return get_bot(bot_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown bot: {bot_id}") from None


def _can_view(record: RunRecord, identity: Optional[str]) -> bool:
    if record.owner is None:
        return True
    try:
        ensure_owner_access(identity, record.owner)
    except (PermissionDeniedError, FileNotFoundError):
        return False
    return True


def _visible_runs(bot: Bot, identity: Optional[str], limit: Optional[int] = None) -> List[RunRecord]:
    records = [r for r in list_runs(bot.id) if _can_view(r, identity)]
    return records[:limit] if limit is not None else records


def _summary(bot: Bot, identity: Optional[str]) -> Dict[str, Any]:
    settings = load_settings(bot)
    all_runs = list_runs(bot.id)
    visible = [r for r in all_runs if _can_view(r, identity)]
    schedule = bot.default_schedule
    return {
        "id": bot.id,
        "name": bot.name,
        "description": bot.description,
        "kind": bot.kind,
        "scope": bot.scope,
        "enabled": settings.enabled,
        "cadence": settings.cadence,
        "schedule": schedule.description if schedule else None,
        "next_run": runner.next_due(schedule, settings, all_runs),
        "running": runner.running_record(bot) is not None,
        "last_run": visible[0] if visible else None,
    }


def _detail(bot: Bot, identity: Optional[str]) -> BotDetail:
    settings = load_settings(bot)
    return BotDetail(
        **_summary(bot, identity),
        settings=settings.model_dump(mode="json"),
        settings_schema=bot.settings_model.model_json_schema(),
        can_manage=_is_admin(identity),
    )


@router.get("", response_model=List[BotSummary])
def bots_list(identity: Optional[str] = Depends(get_active_user)) -> List[BotSummary]:
    """Every registered bot with its last visible run and next due time."""

    return [BotSummary(**_summary(bot, identity)) for bot in list_bots()]


@router.get("/{bot_id}", response_model=BotDetail)
def bot_detail(bot_id: str, identity: Optional[str] = Depends(get_active_user)) -> BotDetail:
    """One bot with its settings and their JSON schema."""

    return _detail(_bot_or_404(bot_id), identity)


@router.get("/{bot_id}/runs", response_model=List[RunRecord])
def bot_runs(
    bot_id: str,
    limit: int = Query(20, ge=1, le=MAX_RUNS),
    identity: Optional[str] = Depends(get_active_user),
) -> List[RunRecord]:
    """Run history, newest first, filtered to runs the caller may see."""

    return _visible_runs(_bot_or_404(bot_id), identity, limit)


@router.get("/{bot_id}/runs/{run_id}", response_model=RunRecord)
def bot_run(bot_id: str, run_id: str, identity: Optional[str] = Depends(get_active_user)) -> RunRecord:
    """One run, for polling a run started with Run now."""

    bot = _bot_or_404(bot_id)
    record = get_run(bot.id, run_id)
    if record is None or not _can_view(record, identity):
        raise HTTPException(status_code=404, detail="Run not found")
    return record


@router.post("/{bot_id}/run", response_model=RunRecord, status_code=202)
def bot_run_now(
    bot_id: str,
    background_tasks: BackgroundTasks,
    identity: Optional[str] = Depends(_require_admin),
) -> RunRecord:
    """Start a background run. 409 while another run of this bot is in progress."""

    bot = _bot_or_404(bot_id)
    try:
        record = runner.start_run(bot.id, actor=identity)
    except runner.BotBusyError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "run_id": exc.running.id},
        ) from None
    logger.info(
        "Bot %s run %s started by %s",
        sanitise_log_value(bot.id),
        sanitise_log_value(record.id),
        sanitise_log_value(identity),
    )
    return runner.dispatch_run(record, background_tasks)


@router.put("/{bot_id}/settings", response_model=BotDetail)
def bot_settings_update(
    bot_id: str,
    values: Dict[str, Any],
    identity: Optional[str] = Depends(_require_admin),
) -> BotDetail:
    """Validate and save settings (merged over the current ones), audited."""

    bot = _bot_or_404(bot_id)
    merged = {**load_settings(bot).model_dump(mode="json"), **values}
    try:
        save_settings(bot, merged, actor=identity or ("local" if config.disable_auth else None))
    except ValidationError as exc:
        errors = [
            {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type", "")}
            for err in exc.errors(include_url=False)
        ]
        raise HTTPException(status_code=422, detail=errors) from None
    return _detail(bot, identity)
