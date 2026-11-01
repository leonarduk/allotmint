"""Bots page API: list automated jobs/agents, their runs, Run now and settings (#10477).

Viewing follows owner access: system-scoped runs are visible to any signed-in
user, owner-scoped runs only to callers who can access that owner.

Run now and settings changes need admin (:func:`_is_admin`). Unlike the
local-only MCP-server/app-update gates this route is also served on AWS,
where ``disable_auth`` is true because API Gateway does the Cognito check --
so ``disable_auth`` alone never grants admin. The identity comes from
:func:`backend.auth.get_active_user`, which resolves the Cognito email even
with ``disable_auth`` set.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ValidationError

from backend.auth import get_active_user, is_demo_request
from backend.bots import runner
from backend.bots.local_scheduler import is_scheduled_here
from backend.bots.registry import Bot, BotKind, BotScope, get_bot, list_bots
from backend.bots.run_records import DIGEST_ITEMS_KEY
from backend.bots.runs import MAX_RUNS, RunRecord, get_run, list_runs
from backend.bots.settings import load_settings, save_settings
from backend.common.authz import ensure_owner_access
from backend.common.errors import PermissionDeniedError
from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.routes.bots_digest import is_admin

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
    # False when the bot has a schedule that this server never fires (a
    # local server outside ``local_bot_schedule``, #10925).
    scheduled_here: bool = False
    overdue: bool = False
    running: bool = False
    last_run: Optional[RunRecord] = None


class BotDetail(BotSummary):
    settings: Dict[str, Any]
    settings_schema: Dict[str, Any]
    can_manage: bool = False


def _admin_emails() -> set[str]:
    """``ADMIN_EMAILS`` when set (as ``backend.common.admin``), else ``allowed_emails``."""

    raw = os.getenv("ADMIN_EMAILS", "")
    admins = {e.strip().lower() for e in raw.split(",") if e.strip()}
    if admins:
        return admins
    return {e.strip().lower() for e in (config.allowed_emails or []) if isinstance(e, str) and e.strip()}


def _is_admin(identity: Optional[str]) -> bool:
    """Whether ``identity`` may start runs and change settings.

    Demo tokens never. Local dev with auth off (the usual single-user setup)
    always. Anywhere else -- including the AWS Lambda, which runs with
    ``disable_auth`` -- only a caller on the admin allowlist; with no
    allowlist configured, nobody.
    """

    if is_demo_request():
        return False
    if config.disable_auth and config.app_env == "local":
        return True
    return isinstance(identity, str) and identity.strip().lower() in _admin_emails()


def _require_admin(identity: Optional[str] = Depends(get_active_user)) -> Optional[str]:
    if not _is_admin(identity):
        raise HTTPException(status_code=403, detail=_FORBIDDEN_DETAIL)
    return identity


def _bot_or_404(bot_id: str) -> Bot:
    try:
        return get_bot(bot_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown bot: {bot_id}") from None


def _can_access_owner(owner: Optional[str], identity: Optional[str]) -> bool:
    if owner is None:
        return True
    try:
        ensure_owner_access(identity, owner)
    except (PermissionDeniedError, FileNotFoundError):
        return False
    return True


def _can_view(record: RunRecord, identity: Optional[str]) -> bool:
    return _can_access_owner(record.owner, identity)


def _redacted(record: RunRecord, identity: Optional[str]) -> RunRecord:
    """``record`` without the digest items about owners the caller cannot access.

    A run over every owner is visible to everyone, but its ``digest_items``
    name owners (#10502): each owner's items are served only to callers with
    access to that owner, and system-wide items (``owner`` is None) only to
    admins, the same rule as ``GET /bots/digest`` (``bots_digest.is_admin``).
    """

    items = record.report.get(DIGEST_ITEMS_KEY) if record.report else None
    if not isinstance(items, list):
        return record
    access: Dict[str, bool] = {}
    admin: List[bool] = []

    def visible(item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        owner = item.get("owner")
        if owner is None:
            if not admin:
                admin.append(is_admin(identity))
            return admin[0]
        if not isinstance(owner, str):
            return False
        if owner not in access:
            access[owner] = _can_access_owner(owner, identity)
        return access[owner]

    report = {**(record.report or {}), DIGEST_ITEMS_KEY: [item for item in items if visible(item)]}
    return record.model_copy(update={"report": report})


def _visible_runs(bot: Bot, identity: Optional[str], limit: Optional[int] = None) -> List[RunRecord]:
    records = [_redacted(r, identity) for r in list_runs(bot.id) if _can_view(r, identity)]
    return records[:limit] if limit is not None else records


def _summary(bot: Bot, identity: Optional[str]) -> Dict[str, Any]:
    settings = load_settings(bot)
    all_runs = list_runs(bot.id)
    visible = [r for r in all_runs if _can_view(r, identity)]
    schedule = bot.default_schedule if is_scheduled_here(bot, config) else None
    return {
        "id": bot.id,
        "name": bot.name,
        "description": bot.description,
        "kind": bot.kind,
        "scope": bot.scope,
        "enabled": settings.enabled,
        "cadence": settings.cadence,
        "schedule": bot.default_schedule.description if bot.default_schedule else None,
        "next_run": runner.next_due(schedule, settings, all_runs),
        "scheduled_here": schedule is not None,
        "overdue": runner.is_overdue(schedule, settings, all_runs),
        "running": runner.running_record(bot) is not None,
        "last_run": _redacted(visible[0], identity) if visible else None,
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
    return _redacted(record, identity)


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
