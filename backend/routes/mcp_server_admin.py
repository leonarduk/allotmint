"""Status and restart of the local allotmint-pro MCP server from the Support page.

Only registered when ``config.app_env == "local"`` (see
``backend/bootstrap/routers.py``): on AWS the MCP server is a Lambda, so there
is no process to inspect or restart and the route 404s.

The MCP server imports the backend and allotmint-pro once at startup, so
merged code changes only take effect after a restart. Status reports whether
code changed after the running server started; restart stops it and starts a
fresh one in the background with the same launcher a terminal would use.

Safety rules for stopping (see ``backend/utils/mcp_server_process.py``):

- only a local ``MCP_SERVER_URL`` (plain-HTTP localhost) is managed;
- only the process listening on that port is stopped, and only when its
  command line names ``allotmint_pro.mcp_server.app:app`` -- plus its parent
  when that is the Windows venv launcher with the same command line;
- a port held by anything else refuses the restart with a reason.

Bad states never raise: they come back as ``reason`` in the response body.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.routes import get_active_user
from backend.utils import mcp_server_process as mcp_process
from backend.utils.mcp_server_process import McpProcessError, PortOwner

logger = logging.getLogger(__name__)

_FORBIDDEN_DETAIL = "Not authorized to manage the MCP server"
_DEFAULT_PORT = 8001
_START_TIMEOUT_SECONDS = 90
_TOOLS_TIMEOUT_SECONDS = 10
_GIT_TIMEOUT_SECONDS = 15
# Same rule as Start-LocalMcpServer (run-backend.ps1) / start_mcp_server.sh.
_LOCAL_URL = re.compile(r"^http://(?:localhost|127\.0\.0\.1)(?::(\d+))?(?:/|$)")

# Serialises restarts: two concurrent restarts would race to stop and bind
# the same port.
_restart_lock = threading.Lock()


def _ensure_admin_access(identity: str | None = Depends(get_active_user)) -> None:
    """Restrict to the deployment's configured owner email(s).

    Same gate as ``backend/routes/app_update.py``. No-ops when auth is
    disabled (the usual local setup).
    """

    if config.disable_auth:
        return
    allowed = {
        email.strip().lower() for email in (config.allowed_emails or []) if isinstance(email, str) and email.strip()
    }
    if not identity or identity.strip().lower() not in allowed:
        raise HTTPException(status_code=403, detail=_FORBIDDEN_DETAIL)


router = APIRouter(
    prefix="/support/mcp-server",
    tags=["support"],
    dependencies=[Depends(_ensure_admin_access)],
)


class McpServerStatus(BaseModel):
    can_restart: bool = False
    reason: str | None = None
    url: str | None = None
    port: int | None = None
    running: bool = False
    pid: int | None = None
    parent_pid: int | None = None
    started_at: datetime | None = None
    pro_dir: str | None = None
    pro_commit: str | None = None
    code_changed: bool = False
    code_changes: list[str] = []
    tool_count: int | None = None
    tools_error: str | None = None
    log_path: str | None = None


class McpServerRestartResult(BaseModel):
    restarted: bool
    reason: str | None = None
    stopped_pids: list[int] = []
    pid: int | None = None
    tool_count: int | None = None
    log_lines: list[str] = []
    log_path: str | None = None


def _repo_root() -> Path:
    return Path(config.repo_root or Path.cwd())


def _log_path() -> Path:
    return _repo_root() / "logs" / "mcp-server.log"


def _resolve_target() -> tuple[str | None, int | None, str | None]:
    """Return ``(url, port, reason)``; ``reason`` is set when not manageable."""

    url = (config.mcp_server_url or "").strip()
    if url:
        match = _LOCAL_URL.match(url)
        if not match:
            return url, None, "MCP_SERVER_URL is not a plain-HTTP localhost URL; only a local server can be managed."
        port_text = match.group(1) or "80"
    else:
        port_text = os.environ.get("MCP_SERVER_PORT", "").strip() or str(_DEFAULT_PORT)
        url = f"http://localhost:{port_text}/mcp"
    if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
        return url, None, f"Invalid MCP server port '{port_text}' (expected 1-65535)."
    return url, int(port_text), None


def _pro_dir() -> Path:
    """The allotmint-pro checkout, looked up as the launch scripts do."""

    override = os.environ.get("ALLOTMINT_PRO_DIR", "").strip()
    return Path(override) if override else _repo_root().parent / "allotmint-pro"


def _git_head(root: Path) -> tuple[str, float] | None:
    """``(sha, commit time)`` of HEAD in ``root``, or ``None`` if unreadable."""

    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%H %ct"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("Reading git HEAD in %s failed: %s", sanitise_log_value(root), sanitise_log_value(exc))
        return None
    parts = proc.stdout.split()
    if proc.returncode != 0 or len(parts) != 2:
        return None
    return parts[0], float(parts[1])


def _newest_source(source_dir: Path) -> tuple[Path, float] | None:
    """The most recently modified ``.py`` file under ``source_dir``."""

    newest: tuple[Path, float] | None = None
    for dirpath, dirnames, filenames in os.walk(source_dir):
        dirnames[:] = [name for name in dirnames if name != "__pycache__" and not name.startswith(".")]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            path = Path(dirpath) / name
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue  # deleted between listing and stat; it can't be the newest file

            if newest is None or mtime > newest[1]:
                newest = (path, mtime)
    return newest


def _code_changes(started_at: float, pro_dir: Path) -> list[str]:
    """What changed in allotmint-pro or allotmint ``backend/`` after ``started_at``.

    Both a newer commit and newer source files count: a fast-forward pull
    brings commits dated before the server started, but rewrites the files.
    """

    changes = []
    for label, root, source in (
        ("allotmint-pro", pro_dir, pro_dir / "allotmint_pro"),
        ("allotmint", _repo_root(), _repo_root() / "backend"),
    ):
        head = _git_head(root)
        if head and head[1] > started_at:
            changes.append(f"{label}: commit {head[0][:7]} is newer than the running server.")
        newest = _newest_source(source)
        if newest and newest[1] > started_at:
            changes.append(f"{label}: {newest[0].relative_to(root).as_posix()} changed after the server started.")
    return changes


async def _tool_count(url: str) -> int:
    from backend.chat.mcp_tools_client import mcp_session

    async def _list() -> int:
        async with mcp_session(url) as session:
            result = await session.list_tools()
        return len(result.tools)

    return await asyncio.wait_for(_list(), timeout=_TOOLS_TIMEOUT_SECONDS)


def _describe_owners(status: McpServerStatus, owners: list[PortOwner]) -> None:
    """Fill the process fields; set ``reason`` if the port holder isn't ours."""

    foreign = [owner.process for owner in owners if not owner.process.is_mcp_server]
    if foreign:
        holder = foreign[0]
        command = holder.command_line or "unknown command"
        status.reason = (
            f"Port {status.port} is held by another program (pid {holder.pid}: {command[:200]}); "
            "it is not the allotmint-pro MCP server, so it will not be stopped."
        )
        return
    if not owners:
        return
    process = owners[0].process
    status.running = True
    status.pid = process.pid
    status.parent_pid = owners[0].parent.pid if owners[0].parent and owners[0].parent.is_mcp_server else None
    if process.started_at is not None:
        status.started_at = datetime.fromtimestamp(process.started_at, tz=timezone.utc)


async def _collect_status(include_details: bool) -> tuple[McpServerStatus, list[PortOwner]]:
    url, port, reason = _resolve_target()
    status = McpServerStatus(url=url, port=port, reason=reason, log_path=str(_log_path()))
    if reason or port is None:
        return status, []
    pro_dir = _pro_dir()
    status.pro_dir = str(pro_dir)
    if not (pro_dir / "allotmint_pro" / "mcp_server").is_dir():
        status.reason = f"allotmint-pro not found at {pro_dir}; clone it there or set ALLOTMINT_PRO_DIR."
        return status, []
    try:
        owners = await run_in_threadpool(mcp_process.find_port_owners, port)
    except McpProcessError as exc:
        status.reason = str(exc)
        return status, []
    _describe_owners(status, owners)
    status.can_restart = status.reason is None
    if include_details:
        await _add_details(status, pro_dir)
    return status, owners


async def _add_details(status: McpServerStatus, pro_dir: Path) -> None:
    head = await run_in_threadpool(_git_head, pro_dir)
    status.pro_commit = head[0] if head else None
    if not status.running or status.url is None:
        return
    if status.started_at is not None:
        status.code_changes = await run_in_threadpool(_code_changes, status.started_at.timestamp(), pro_dir)
        status.code_changed = bool(status.code_changes)
    try:
        status.tool_count = await _tool_count(status.url)
    except Exception as exc:  # noqa: BLE001 - reported in the response, not swallowed
        logger.warning("Listing MCP tools failed: %s", sanitise_log_value(exc))
        status.tools_error = "Could not list the MCP server's tools; see the backend log for details."


async def _wait_until_ready(launcher: subprocess.Popen, url: str, port: int) -> tuple[int | None, str | None]:
    """Wait for the port and a successful ``tools/list``: ``(tool_count, error)``."""

    loop = asyncio.get_running_loop()
    deadline = loop.time() + _START_TIMEOUT_SECONDS
    last_error = ""
    while loop.time() < deadline:
        exit_code = launcher.poll()
        if exit_code is not None:
            return None, f"The MCP server launcher exited with code {exit_code}."
        if await run_in_threadpool(mcp_process.port_listening, port):
            try:
                return await _tool_count(url), None
            except Exception as exc:  # noqa: BLE001 - retried until the deadline, then reported
                last_error = f" Last tools/list error: {exc}"
        await asyncio.sleep(1)
    return None, (
        f"The MCP server did not answer tools/list within {_START_TIMEOUT_SECONDS}s "
        f"(launcher pid {launcher.pid} left running).{last_error}"
    )


async def _restart(status: McpServerStatus, owners: list[PortOwner]) -> McpServerRestartResult:
    log_path = _log_path()
    if status.port is None or status.url is None:
        return McpServerRestartResult(restarted=False, reason="No MCP server port configured.", log_path=str(log_path))
    stopped = [pid for owner in owners for pid in owner.pids_to_stop()]
    if stopped:
        await run_in_threadpool(mcp_process.stop_processes, stopped, status.port)
        logger.info("Stopped MCP server process(es) %s", sanitise_log_value(stopped))
    offset = mcp_process.log_size(log_path)
    launcher = await run_in_threadpool(mcp_process.start_server, _repo_root(), status.port, log_path)
    tool_count, error = await _wait_until_ready(launcher, status.url, status.port)
    result = McpServerRestartResult(restarted=error is None, reason=error, stopped_pids=stopped, log_path=str(log_path))
    if error:
        result.log_lines = mcp_process.read_log_tail(log_path, offset)
        logger.warning("MCP server restart failed: %s", sanitise_log_value(error))
        return result
    result.tool_count = tool_count
    new_owners = await run_in_threadpool(mcp_process.find_port_owners, status.port)
    result.pid = new_owners[0].process.pid if new_owners else None
    logger.info(
        "MCP server restarted (pid %s, %s tools)", sanitise_log_value(result.pid), sanitise_log_value(tool_count)
    )
    return result


@router.get("/status", response_model=McpServerStatus)
async def get_mcp_server_status() -> McpServerStatus:
    """Report whether the local MCP server runs, since when, and on what code."""

    status, _ = await _collect_status(include_details=True)
    return status


@router.post("/restart", response_model=McpServerRestartResult)
async def post_mcp_server_restart() -> McpServerRestartResult:
    """Stop the local allotmint-pro MCP server (if running) and start a fresh one."""

    if not _restart_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A restart is already in progress.")
    try:
        status, owners = await _collect_status(include_details=False)
        if not status.can_restart:
            return McpServerRestartResult(restarted=False, reason=status.reason, log_path=status.log_path)
        return await _restart(status, owners)
    except McpProcessError as exc:
        logger.warning("MCP server restart failed: %s", sanitise_log_value(exc))
        return McpServerRestartResult(
            restarted=False,
            reason=str(exc),
            log_lines=mcp_process.read_log_tail(_log_path()),
            log_path=str(_log_path()),
        )
    finally:
        _restart_lock.release()
