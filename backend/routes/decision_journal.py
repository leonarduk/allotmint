# backend/routes/decision_journal.py
"""Owner-scoped decision journal routes (#10481).

Access and storage follow ``/plans/{owner}`` (see
:mod:`backend.routes.investment_plan`): the journal sidecar sits beside the
plans directory under the accounts root the request was authorised against.

Drafts are returned, never stored; only ``POST .../entries`` with
``"confirmed": true`` and the owner's own ``reason`` writes to the plan.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.auth import get_active_user
from backend.common.investment_plan import InvestmentPlan, PlanNotFoundError, load_plan
from backend.decision_journal.bot import run_for_owner
from backend.decision_journal.capture import (
    default_context_tools,
    lookback_window,
    plan_change_draft,
    qualifying_trades,
    trade_change,
    trade_draft,
)
from backend.decision_journal.entries import (
    ConfirmDecision,
    DuplicateDecisionError,
    confirm_decision,
    dismiss_change,
    set_lesson,
    set_threshold,
)
from backend.decision_journal.store import load_journal
from backend.routes.investment_plan import _data_root, _resolve_owner, _validation_detail

router = APIRouter(tags=["decision-journal"])


class DraftRequest(BaseModel):
    """Either a transaction id, or the plan target before and after an edit."""

    model_config = ConfigDict(extra="forbid")

    source_ref: Optional[str] = None
    previous_target: Optional[Dict[str, float]] = None
    target: Optional[Dict[str, float]] = None


class DismissRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ref: str = Field(min_length=1)


class LessonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson: str = Field(max_length=2000)


class SettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold_gbp: float = Field(ge=0)


def _owner_transactions(request: Request, owner: str) -> List[Mapping[str, Any]]:
    from backend.routes.transactions import load_all_transactions, resolve_writable_store

    store, _kind = resolve_writable_store(request)
    return [tx.model_dump() for tx in load_all_transactions(store) if tx.owner.lower() == owner.lower()]


def _plan_or_none(owner: str, data_root: Path) -> Optional[InvestmentPlan]:
    try:
        return load_plan(owner, data_root)
    except (PlanNotFoundError, ValidationError, ValueError):
        return None  # a draft is still useful without a plan's vehicle classes


@router.get("/decision-journal/{owner}")
def get_journal(owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    journal = load_journal(owner, _data_root(accounts_root))
    since, until = lookback_window(date.today())
    unlogged = qualifying_trades(
        _owner_transactions(request, owner),
        threshold_gbp=journal.settings.threshold_gbp,
        handled_refs=journal.handled_refs(),
        since=since,
        until=until,
    )
    body = journal.model_dump(mode="json", exclude_none=True)
    return {"settings": body["settings"], "entries": body["entries"], "unlogged": unlogged}


@router.post("/decision-journal/{owner}/drafts")
def create_draft(owner: str, request: Request, body: DraftRequest, identity: Optional[str] = Depends(get_active_user)):
    """A pre-filled draft for the owner to complete. Nothing is saved."""
    owner, accounts_root = _resolve_owner(request, owner, identity)
    if body.source_ref:
        tx = next((t for t in _owner_transactions(request, owner) if t.get("id") == body.source_ref), None)
        change = trade_change(tx) if tx else None
        if change is None:
            raise HTTPException(status_code=404, detail=f"No BUY/SELL transaction {body.source_ref} for {owner}")
        tools = default_context_tools(owner, accounts_root)
        return trade_draft(change, tools, plan=_plan_or_none(owner, _data_root(accounts_root)))
    if body.previous_target is not None and body.target is not None:
        draft = plan_change_draft(body.previous_target, body.target)
        if draft is None:
            raise HTTPException(status_code=400, detail="The plan target did not change")
        return draft
    raise HTTPException(status_code=400, detail="Send source_ref, or previous_target and target")


@router.post("/decision-journal/{owner}/entries", status_code=201)
def post_entry(
    owner: str,
    request: Request,
    body: Dict[str, Any] = Body(...),
    identity: Optional[str] = Depends(get_active_user),
):
    """Log a decision the owner has confirmed: appended to the plan, context to the journal."""
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        confirmed = ConfirmDecision.model_validate(body)
        entry = confirm_decision(owner, confirmed, _data_root(accounts_root))
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=_validation_detail(exc)) from exc
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"{exc}; save a plan before logging decisions") from exc
    except DuplicateDecisionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return entry.model_dump(mode="json", exclude_none=True)


@router.post("/decision-journal/{owner}/dismissed")
def post_dismissed(
    owner: str, request: Request, body: DismissRequest, identity: Optional[str] = Depends(get_active_user)
):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    dismiss_change(owner, body.source_ref, _data_root(accounts_root))
    return {"dismissed": body.source_ref}


@router.put("/decision-journal/{owner}/entries/{entry_id}/reviews/{horizon_months}/lesson")
def put_lesson(
    owner: str,
    entry_id: str,
    horizon_months: int,
    request: Request,
    body: LessonRequest,
    identity: Optional[str] = Depends(get_active_user),
):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    try:
        set_lesson(owner, entry_id, horizon_months, body.lesson, _data_root(accounts_root))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"entry_id": entry_id, "horizon_months": horizon_months, "lesson": body.lesson.strip() or None}


@router.put("/decision-journal/{owner}/settings")
def put_settings(
    owner: str, request: Request, body: SettingsRequest, identity: Optional[str] = Depends(get_active_user)
):
    owner, accounts_root = _resolve_owner(request, owner, identity)
    set_threshold(owner, body.threshold_gbp, _data_root(accounts_root))
    return {"threshold_gbp": body.threshold_gbp}


@router.post("/decision-journal/{owner}/run")
def run_now(owner: str, request: Request, identity: Optional[str] = Depends(get_active_user)):
    """The daily run for one owner: list unlogged changes and run due reviews."""
    owner, accounts_root = _resolve_owner(request, owner, identity)
    return run_for_owner(
        owner, _owner_transactions(request, owner), as_of=date.today(), data_root=_data_root(accounts_root)
    )
