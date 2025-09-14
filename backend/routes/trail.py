from fastapi import APIRouter, Depends, HTTPException

from backend.auth import get_current_user
from backend.config import config
from backend.quests import trail

router = APIRouter(prefix="/trail", tags=["trail"])


if config.disable_auth:

    @router.get("")
    async def list_tasks():
        """Return tasks for the demo user when authentication is disabled."""
        return {"tasks": trail.get_tasks("demo")}

    @router.post("/{task_id}/complete")
    async def complete_task(task_id: str):
        """Mark ``task_id`` complete for the demo user when auth is disabled."""
        try:
            tasks = trail.mark_complete("demo", task_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"tasks": tasks}

else:

    @router.get("")
    async def list_tasks(current_user: str = Depends(get_current_user)):
        """Return tasks for the authenticated user."""
        return {"tasks": trail.get_tasks(current_user)}

    @router.post("/{task_id}/complete")
    async def complete_task(task_id: str, current_user: str = Depends(get_current_user)):
        """Mark ``task_id`` complete for the authenticated user."""
        try:
            tasks = trail.mark_complete(current_user, task_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"tasks": tasks}
