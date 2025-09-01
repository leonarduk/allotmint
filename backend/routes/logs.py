from collections import deque
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from backend.config import config

router = APIRouter(prefix="/logs", tags=["logs"])

_DEFAULT_LINES = 200


@router.get("", response_class=PlainTextResponse)
async def read_logs(lines: int = _DEFAULT_LINES) -> str:
    """Return the latest lines from ``backend.log``.

    Parameters
    ----------
    lines:
        Maximum number of lines to return, defaults to ``_DEFAULT_LINES``.
    """
    root = Path(config.repo_root or Path.cwd())
    log_file = root / "backend.log"
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    try:
        with log_file.open("r", encoding="utf-8") as fh:
            content = "".join(deque(fh, maxlen=lines))
        return content
    except Exception as exc:  # pragma: no cover - unexpected errors
        raise HTTPException(status_code=500, detail=str(exc))
