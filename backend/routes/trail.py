from collections.abc import Mapping

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import get_current_user
from backend.config import config, demo_identity
from backend.quests import trail

router = APIRouter(prefix="/trail", tags=["trail"])


if config.disable_auth:

    @router.get("")
    async def list_tasks():
        """Return tasks for the configured demo user when auth is disabled."""
        return trail.get_tasks(demo_identity())

    @router.post("/{task_id}/complete")
    async def complete_task(task_id: str):
        """Mark ``task_id`` complete for the demo user when auth is disabled.

        Returns the updated Trail payload including XP, streak, and daily totals.
        """
        try:
            result = trail.mark_complete(demo_identity(), task_id)
            if isinstance(result, Mapping) and "tasks" in result:
                return result
            return {"tasks": result}
        except KeyError:
            raise HTTPException(status_code=404, detail="Task not found")

else:

    @router.get("")
    async def list_tasks(current_user: str = Depends(get_current_user)):
        """Return tasks for the authenticated user."""
        return trail.get_tasks(current_user)

    @router.post("/{task_id}/complete")
    async def complete_task(task_id: str, current_user: str = Depends(get_current_user)):
        """Mark ``task_id`` complete for the authenticated user.

        Returns the updated Trail payload including XP, streak, and daily totals.
        """
        try:
            result = trail.mark_complete(current_user, task_id)
            if isinstance(result, Mapping) and "tasks" in result:
                return result
            return {"tasks": result}
        except KeyError:
            raise HTTPException(status_code=404, detail="Task not found")
