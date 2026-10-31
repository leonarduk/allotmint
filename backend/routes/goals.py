import math
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.auth import get_current_user
from backend.common.goal_projection import project_completion
from backend.common.goals import (
    Goal,
    GoalHistoryConflict,
    add_goal,
    delete_goal,
    load_goal_history,
    load_goals,
    record_goal_amount,
    rename_goal_history,
    save_goals,
)
from backend.common.rebalance import suggest_trades
from backend.config import config, demo_identity

router = APIRouter(prefix="/goals", tags=["goals"])
DEMO_OWNER = demo_identity()


class GoalPayload(BaseModel):
    name: str
    target_amount: float
    target_date: date


class GoalResponse(GoalPayload):
    # ``progress`` and ``current_amount`` are None when the amount saved is
    # unknown, so the UI never shows a misleading 0% (#7829).
    progress: float | None = None
    current_amount: float | None = None
    trades: List[dict] | None = None
    # Built only from *recorded* history (POST /goals/{name}/progress); an
    # ad-hoc ``current_amount`` on GET drives progress but never the projection.
    projection: dict | None = None


class ProgressPayload(BaseModel):
    # Validated in ``_record_progress``: a pydantic constraint would echo inf/nan
    # back in the 422 body, which FastAPI then fails to JSON-encode.
    amount: float
    # Defaults to today when omitted.
    on: date | None = None


def _list_goals(owner: str) -> List[GoalPayload]:
    goals = load_goals(owner)
    return [GoalPayload.model_validate(g.to_dict()) for g in goals]


def _create_goal(owner: str, payload: GoalPayload) -> GoalPayload:
    goal = Goal(payload.name, payload.target_amount, payload.target_date)
    add_goal(owner, goal)
    return GoalPayload.model_validate(goal.to_dict())


def _find_goal(owner: str, name: str) -> Goal:
    for g in load_goals(owner):
        if g.name == name:
            return g
    raise HTTPException(status_code=404, detail="Goal not found")


def _goal_response(goal: Goal, current_amount: float | None, history: List[tuple[date, float]]) -> GoalResponse:
    """Build the detail response; an omitted amount falls back to the latest recorded one."""
    if current_amount is None and history:
        current_amount = history[-1][1]
    progress = trades = None
    if current_amount is not None:
        progress = goal.progress(current_amount)
        actual = {"goal": current_amount, "cash": max(goal.target_amount - current_amount, 0.0)}
        trades = suggest_trades(actual, {"goal": 1.0})
    projection = project_completion(history, goal.target_amount, goal.target_date).to_dict()
    return GoalResponse.model_validate(
        {
            **goal.to_dict(),
            "progress": progress,
            "current_amount": current_amount,
            "trades": trades,
            "projection": projection,
        }
    )


def _get_goal(owner: str, name: str, current_amount: float | None = None) -> GoalResponse:
    goal = _find_goal(owner, name)
    return _goal_response(goal, current_amount, load_goal_history(owner, name))


def _record_progress(owner: str, name: str, payload: ProgressPayload) -> GoalResponse:
    # inf/nan would be persisted as non-standard JSON and poison the projection.
    if not math.isfinite(payload.amount) or payload.amount < 0:
        raise HTTPException(status_code=422, detail="amount must be a finite number of zero or more")
    on = payload.on or date.today()
    if on > date.today():
        raise HTTPException(status_code=422, detail="progress cannot be recorded for a future date")
    goal = _find_goal(owner, name)
    history = record_goal_amount(owner, name, payload.amount, on)
    return _goal_response(goal, payload.amount, history)


_NAME_CONFLICT = "Another goal already uses that name"


def _update_goal(owner: str, name: str, payload: GoalPayload) -> GoalPayload:
    goals = load_goals(owner)
    for idx, g in enumerate(goals):
        if g.name == name:
            # Renaming onto another goal would merge the two and clobber its history.
            if payload.name != name and any(o.name == payload.name for o in goals):
                raise HTTPException(status_code=409, detail=_NAME_CONFLICT)
            goals[idx] = Goal(payload.name, payload.target_amount, payload.target_date)
            # Move the history first so a failure there leaves the goal untouched;
            # if saving the goal then fails, move it back.
            try:
                rename_goal_history(owner, name, payload.name)
            except GoalHistoryConflict as exc:
                raise HTTPException(status_code=409, detail=_NAME_CONFLICT) from exc
            try:
                save_goals(owner, goals)
            except Exception:
                rename_goal_history(owner, payload.name, name)
                raise
            return GoalPayload(**payload.model_dump())
    raise HTTPException(status_code=404, detail="Goal not found")


def _remove_goal(owner: str, name: str) -> dict:
    goals = load_goals(owner)
    if not any(g.name == name for g in goals):
        raise HTTPException(status_code=404, detail="Goal not found")
    delete_goal(owner, name)
    return {"status": "deleted"}


if config.disable_auth:

    @router.get("/")
    def list_goals() -> List[GoalPayload]:
        return _list_goals(DEMO_OWNER)

    @router.post("/")
    def create_goal(payload: GoalPayload) -> GoalPayload:
        return _create_goal(DEMO_OWNER, payload)

    @router.get("/{name}")
    def get_goal(name: str, current_amount: float | None = Query(None, allow_inf_nan=False)) -> GoalResponse:
        return _get_goal(DEMO_OWNER, name, current_amount)

    @router.post("/{name}/progress")
    def record_progress(name: str, payload: ProgressPayload) -> GoalResponse:
        return _record_progress(DEMO_OWNER, name, payload)

    @router.put("/{name}")
    def update_goal(name: str, payload: GoalPayload) -> GoalPayload:
        return _update_goal(DEMO_OWNER, name, payload)

    @router.delete("/{name}")
    def remove_goal(name: str) -> dict:
        return _remove_goal(DEMO_OWNER, name)

else:
    # The handlers below redefine names from the if-branch (list_goals, create_goal, etc.).
    # mypy raises [misc] for conditional function redefinitions at module scope — a known
    # limitation. Both branches are mutually exclusive at runtime via config.disable_auth.

    @router.get("/")
    def list_goals(current_user: str = Depends(get_current_user)) -> List[GoalPayload]:  # type: ignore[misc]
        return _list_goals(current_user)

    @router.post("/")
    def create_goal(  # type: ignore[misc]
        payload: GoalPayload, current_user: str = Depends(get_current_user)
    ) -> GoalPayload:
        return _create_goal(current_user, payload)

    @router.get("/{name}")
    def get_goal(  # type: ignore[misc]
        name: str,
        current_amount: float | None = Query(None, allow_inf_nan=False),
        current_user: str = Depends(get_current_user),
    ) -> GoalResponse:
        return _get_goal(current_user, name, current_amount)

    @router.post("/{name}/progress")
    def record_progress(  # type: ignore[misc]
        name: str, payload: ProgressPayload, current_user: str = Depends(get_current_user)
    ) -> GoalResponse:
        return _record_progress(current_user, name, payload)

    @router.put("/{name}")
    def update_goal(  # type: ignore[misc]
        name: str, payload: GoalPayload, current_user: str = Depends(get_current_user)
    ) -> GoalPayload:
        return _update_goal(current_user, name, payload)

    @router.delete("/{name}")
    def remove_goal(name: str, current_user: str = Depends(get_current_user)) -> dict:  # type: ignore[misc]
        return _remove_goal(current_user, name)
