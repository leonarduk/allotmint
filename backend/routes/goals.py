from __future__ import annotations

from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import get_current_user
from backend.common.goals import Goal, add_goal, delete_goal, load_goals, save_goals
from backend.common.rebalance import suggest_trades

router = APIRouter(prefix="/goals", tags=["goals"])


class GoalPayload(BaseModel):
    name: str
    target_amount: float
    target_date: date


class GoalResponse(GoalPayload):
    progress: float | None = None
    trades: List[dict] | None = None


@router.get("/")
async def list_goals(current_user: str = Depends(get_current_user)) -> List[GoalPayload]:
    goals = load_goals(current_user)
    return [GoalPayload(**g.to_dict()) for g in goals]


@router.post("/")
async def create_goal(payload: GoalPayload, current_user: str = Depends(get_current_user)) -> GoalPayload:
    goal = Goal(payload.name, payload.target_amount, payload.target_date)
    add_goal(current_user, goal)
    return GoalPayload(**goal.to_dict())


@router.get("/{name}")
async def get_goal(
    name: str,
    current_amount: float,
    current_user: str = Depends(get_current_user),
) -> GoalResponse:
    goals = load_goals(current_user)
    for g in goals:
        if g.name == name:
            progress = g.progress(current_amount)
            actual = {"goal": current_amount, "cash": max(g.target_amount - current_amount, 0.0)}
            trades = suggest_trades(actual, {"goal": 1.0})
            return GoalResponse(**g.to_dict(), progress=progress, trades=trades)
    raise HTTPException(status_code=404, detail="Goal not found")


@router.put("/{name}")
async def update_goal(
    name: str,
    payload: GoalPayload,
    current_user: str = Depends(get_current_user),
) -> GoalPayload:
    goals = load_goals(current_user)
    found = False
    for idx, g in enumerate(goals):
        if g.name == name:
            goals[idx] = Goal(payload.name, payload.target_amount, payload.target_date)
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Goal not found")
    save_goals(current_user, goals)
    return GoalPayload(**payload.model_dump())


@router.delete("/{name}")
async def remove_goal(name: str, current_user: str = Depends(get_current_user)) -> dict:
    goals = load_goals(current_user)
    if not any(g.name == name for g in goals):
        raise HTTPException(status_code=404, detail="Goal not found")
    delete_goal(current_user, name)
    return {"status": "deleted"}
