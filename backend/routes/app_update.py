"""Self-update of a local git checkout from the Support page.

Only registered when ``config.app_env == "local"`` (see
``backend/bootstrap/routers.py``): on AWS the code runs from an immutable
Lambda image built by CI, so there is no checkout to pull into and the route
404s. Updating there means running the deploy pipeline, not this endpoint.

The update is deliberately conservative: it only ever fast-forwards the
current branch to its configured upstream. A dirty working tree, a detached
HEAD, a branch without an upstream, or local commits not on the upstream all
refuse the update rather than risk losing work. Dependencies are never
reinstalled from here -- the response lists changed dependency manifests so
the user knows to re-run the setup step themselves.

Running processes pick the new code up the same way they pick up local edits:
uvicorn's ``--reload`` (on by default in ``run-local-api.sh`` /
``run-backend.ps1``) restarts the backend when files under ``backend/``
change, and the Vite dev server hot-reloads the frontend.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.config import config
from backend.logging_setup import sanitise_log_value
from backend.routes import get_active_user

logger = logging.getLogger(__name__)

_GIT_TIMEOUT_SECONDS = 60
_FORBIDDEN_DETAIL = "Not authorized to update the application"

# Manifests whose change means `pip install` / `npm install` must be re-run.
_DEPENDENCY_MANIFESTS = frozenset(
    {
        "requirements.txt",
        "requirements-dev.txt",
        "backend/requirements.txt",
        "package.json",
        "package-lock.json",
        "frontend/package.json",
        "frontend/package-lock.json",
    }
)

# Serialises updates: two concurrent fast-forwards against the same checkout
# would race on .git/index.lock and fail confusingly.
_update_lock = threading.Lock()


def _ensure_admin_access(identity: str | None = Depends(get_active_user)) -> None:
    """Restrict updates to the deployment's configured owner email(s).

    Same gate as ``backend/routes/aws_costs_admin.py``: pulling new code is an
    owner action, not something every authenticated family member should be
    able to trigger. No-ops when auth is disabled (the usual local setup).
    """

    if config.disable_auth:
        return
    allowed = {
        email.strip().lower() for email in (config.allowed_emails or []) if isinstance(email, str) and email.strip()
    }
    if not identity or identity.strip().lower() not in allowed:
        raise HTTPException(status_code=403, detail=_FORBIDDEN_DETAIL)


router = APIRouter(
    prefix="/support/app-update",
    tags=["support"],
    dependencies=[Depends(_ensure_admin_access)],
)


class GitError(RuntimeError):
    """A git command exited non-zero or could not be run."""


class AppUpdateStatus(BaseModel):
    can_update: bool
    reason: str | None = None
    branch: str | None = None
    upstream: str | None = None
    current_commit: str | None = None
    upstream_commit: str | None = None
    behind: int = 0
    ahead: int = 0
    dirty: bool = False


class AppUpdateResult(BaseModel):
    updated: bool
    previous_commit: str
    current_commit: str
    changed_files: list[str]
    dependencies_changed: list[str]
    backend_changed: bool
    frontend_changed: bool


def _repo_root() -> Path:
    return Path(config.repo_root or Path.cwd())


def _git(*args: str) -> str:
    """Run ``git`` in the repo root and return stripped stdout."""

    # GIT_TERMINAL_PROMPT=0: a fetch that needs credentials must fail fast
    # rather than block the request waiting on a prompt nobody can answer.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=_repo_root(),
            env=env,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git {args[0]} failed: {exc}") from exc
    if proc.returncode != 0:
        raise GitError(f"git {args[0]} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def _branch_and_upstream() -> tuple[str | None, str | None, str | None]:
    """Return ``(branch, upstream, reason)``; ``reason`` is set when unusable."""

    if not (_repo_root() / ".git").exists():
        return None, None, "Not running from a git checkout."
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        return None, None, "HEAD is detached; check out a branch to update."
    try:
        upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    except GitError:
        return branch, None, f"Branch '{branch}' has no upstream configured."
    return branch, upstream, None


def _collect_status(fetch: bool) -> AppUpdateStatus:
    branch, upstream, reason = _branch_and_upstream()
    if reason:
        return AppUpdateStatus(can_update=False, reason=reason, branch=branch)
    if fetch:
        _git("fetch", "--quiet")
    ahead_raw, behind_raw = _git("rev-list", "--left-right", "--count", "HEAD...@{u}").split()
    status = AppUpdateStatus(
        can_update=False,
        branch=branch,
        upstream=upstream,
        current_commit=_git("rev-parse", "HEAD"),
        upstream_commit=_git("rev-parse", "@{u}"),
        ahead=int(ahead_raw),
        behind=int(behind_raw),
        dirty=bool(_git("status", "--porcelain", "--untracked-files=no")),
    )
    status.reason = _blocking_reason(status)
    status.can_update = status.reason is None
    return status


def _blocking_reason(status: AppUpdateStatus) -> str | None:
    if status.dirty:
        return "Working tree has uncommitted changes to tracked files; commit or stash them first."
    if status.ahead:
        return f"Branch has {status.ahead} local commit(s) not on {status.upstream}; it cannot be fast-forwarded."
    if not status.behind:
        return "Already up to date."
    return None


def _apply_update(status: AppUpdateStatus) -> AppUpdateResult:
    previous = status.current_commit or ""
    _git("merge", "--ff-only", "@{u}")
    current = _git("rev-parse", "HEAD")
    changed = [line for line in _git("diff", "--name-only", previous, current).splitlines() if line]
    logger.info(
        "App updated from %s to %s (%s files changed)",
        sanitise_log_value(previous[:12]),
        sanitise_log_value(current[:12]),
        sanitise_log_value(len(changed)),
    )
    return AppUpdateResult(
        updated=True,
        previous_commit=previous,
        current_commit=current,
        changed_files=changed,
        dependencies_changed=[path for path in changed if path in _DEPENDENCY_MANIFESTS],
        backend_changed=any(path.startswith("backend/") for path in changed),
        frontend_changed=any(path.startswith("frontend/") for path in changed),
    )


@router.get("/status", response_model=AppUpdateStatus)
def get_update_status(fetch: bool = True) -> AppUpdateStatus:
    """Report whether the local checkout can be fast-forwarded to its upstream."""

    try:
        return _collect_status(fetch=fetch)
    except GitError as exc:
        logger.warning("App update status check failed: %s", sanitise_log_value(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("", response_model=AppUpdateResult)
def post_update() -> AppUpdateResult:
    """Fetch and fast-forward the current branch to its upstream."""

    if not _update_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="An update is already in progress.")
    try:
        status = _collect_status(fetch=True)
        if not status.can_update:
            raise HTTPException(status_code=409, detail=status.reason)
        return _apply_update(status)
    except GitError as exc:
        logger.warning("App update failed: %s", sanitise_log_value(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        _update_lock.release()
