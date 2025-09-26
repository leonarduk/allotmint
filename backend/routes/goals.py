from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.common.goals import Goal, add_goal, delete_goal, load_goals, save_goals
from backend.common.rebalance import suggest_trades
from backend.auth import get_current_user
from backend.config import config

router = APIRouter(prefix="/goals", tags=["goals"])

DEMO_OWNER = "demo"


class GoalPayload(BaseModel):
    name: str
    target_amount: float
    target_date: date


class GoalResponse(GoalPayload):
    progress: float | None = None
    trades: List[dict] | None = None


def _list_goals(owner: str) -> List[GoalPayload]:
    goals = load_goals(owner)
    return [GoalPayload(**g.to_dict()) for g in goals]


def _create_goal(owner: str, payload: GoalPayload) -> GoalPayload:
    goal = Goal(payload.name, payload.target_amount, payload.target_date)
    add_goal(owner, goal)
    return GoalPayload(**goal.to_dict())


def _get_goal(owner: str, name: str, current_amount: float) -> GoalResponse:
    goals = load_goals(owner)
    for g in goals:
        if g.name == name:
            progress = g.progress(current_amount)
            actual = {"goal": current_amount, "cash": max(g.target_amount - current_amount, 0.0)}
            trades = suggest_trades(actual, {"goal": 1.0})
            return GoalResponse(**g.to_dict(), progress=progress, trades=trades)
    raise HTTPException(status_code=404, detail="Goal not found")


def _update_goal(owner: str, name: str, payload: GoalPayload) -> GoalPayload:
    goals = load_goals(owner)
    for idx, g in enumerate(goals):
        if g.name == name:
            goals[idx] = Goal(payload.name, payload.target_amount, payload.target_date)
            save_goals(owner, goals)
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
    async def list_goals() -> List[GoalPayload]:
        return _list_goals(DEMO_OWNER)

    @router.post("/")
    async def create_goal(payload: GoalPayload) -> GoalPayload:
        return _create_goal(DEMO_OWNER, payload)

    @router.get("/{name}")
    async def get_goal(name: str, current_amount: float) -> GoalResponse:
        return _get_goal(DEMO_OWNER, name, current_amount)

    @router.put("/{name}")
    async def update_goal(name: str, payload: GoalPayload) -> GoalPayload:
        return _update_goal(DEMO_OWNER, name, payload)

    @router.delete("/{name}")
    async def remove_goal(name: str) -> dict:
        return _remove_goal(DEMO_OWNER, name)

else:

    @router.get("/")
    async def list_goals(current_user: str = Depends(get_current_user)) -> List[GoalPayload]:
        return _list_goals(current_user)

    @router.post("/")
    async def create_goal(
        payload: GoalPayload, current_user: str = Depends(get_current_user)
    ) -> GoalPayload:
        return _create_goal(current_user, payload)

    @router.get("/{name}")
    async def get_goal(
        name: str, current_amount: float, current_user: str = Depends(get_current_user)
    ) -> GoalResponse:
        return _get_goal(current_user, name, current_amount)

    @router.put("/{name}")
    async def update_goal(
        name: str, payload: GoalPayload, current_user: str = Depends(get_current_user)
    ) -> GoalPayload:
        return _update_goal(current_user, name, payload)

    @router.delete("/{name}")
    async def remove_goal(name: str, current_user: str = Depends(get_current_user)) -> dict:
        return _remove_goal(current_user, name)
