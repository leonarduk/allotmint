"""Self-update of a local git checkout from the Support page.

Only registered when ``config.app_env == "local"`` (see
``backend/bootstrap/routers.py``): on AWS the code runs from an immutable
Lambda image built by CI, so there is no checkout to pull into and the route
404s. Updating there means running the deploy pipeline, not this endpoint.

The update is deliberately conservative: it only ever fast-forwards the
current branch to its configured upstream. A detached HEAD, a branch without
an upstream, or local commits not on the upstream all refuse the update
rather than risk losing work. A dirty working tree refuses too, unless the
caller opts into ``stash=true``: the fast-forward then runs as a single
``git merge --ff-only --autostash`` so the stash/merge/pop sequence cannot be
interrupted half-way by uvicorn's reloader restarting this process. If the
local changes conflict with the update, they stay in the stash and the
working tree is reset to the clean upstream commit -- leaving conflict
markers in ``backend/`` would break the reloaded app. Dependencies are never
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
    # True when the only obstacle is a dirty tree, i.e. ``POST ?stash=true`` would work.
    can_update_with_stash: bool = False


class AppUpdateResult(BaseModel):
    updated: bool
    previous_commit: str
    current_commit: str
    changed_files: list[str]
    dependencies_changed: list[str]
    backend_changed: bool
    frontend_changed: bool
    stashed: bool = False
    # False when re-applying stashed changes conflicted; they remain in the stash.
    stash_restored: bool = False
    stash_message: str | None = None


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
    status.can_update_with_stash = status.dirty and _blocking_reason(status, ignore_dirty=True) is None
    return status


def _blocking_reason(status: AppUpdateStatus, ignore_dirty: bool = False) -> str | None:
    if status.dirty and not ignore_dirty:
        return "Working tree has uncommitted changes to tracked files; commit or stash them first."
    if status.ahead:
        return f"Branch has {status.ahead} local commit(s) not on {status.upstream}; it cannot be fast-forwarded."
    if not status.behind:
        return "Already up to date."
    return None


def _stash_ref() -> str | None:
    """Return the commit at the top of the stash, or ``None`` when it is empty.

    ``git stash list`` exits 0 with no output for an empty stash, so a real git
    failure still raises instead of being mistaken for "no stash".
    """

    return _git("stash", "list", "-n", "1", "--format=%H") or None


def _apply_update(status: AppUpdateStatus, stash: bool = False) -> AppUpdateResult:
    previous = status.current_commit or ""
    if stash:
        stash_before = _stash_ref()
        _git("merge", "--ff-only", "--autostash", "@{u}")
        result = _build_result(previous)
        result.stashed = True
        result.stash_restored, result.stash_message = _settle_autostash(stash_before, previous)
        return result
    _git("merge", "--ff-only", "@{u}")
    return _build_result(previous)


def _is_autostash_of(stash_commit: str, previous_head: str) -> bool:
    """True when ``stash_commit`` is the autostash git made on top of ``previous_head``."""

    # The stash reflog message (what ``git stash list`` shows) is exactly
    # "autostash" for git's own autostash; the commit subject is "On <branch>: ...".
    # Hash and message are read in one call so they describe the same entry.
    top_hash, _, reflog_message = _git("stash", "list", "-n", "1", "--format=%H %gs").partition(" ")
    return (
        top_hash == stash_commit
        and reflog_message == "autostash"
        and _git("rev-parse", f"{stash_commit}^1") == previous_head
    )


def _settle_autostash(stash_before: str | None, previous_head: str) -> tuple[bool, str | None]:
    """Check whether ``--autostash`` re-applied cleanly; clean up if not.

    git exits 0 even when re-applying the autostash conflicts: it leaves
    conflict markers in the tree and stores the changes as a new stash entry.
    Only when unmerged paths exist *and* the top of the stash is a new entry
    that is provably git's autostash (reflog ``autostash``, parent the
    pre-update HEAD) are the changes known to be safe in the stash, so only then is
    the tree reset to the updated commit to keep the running app importable.
    A cleanly re-applied stash must never reach the reset: it would discard
    the user's restored changes.
    """

    stash_after = _stash_ref()
    unmerged = _git("diff", "--name-only", "--diff-filter=U")
    if not unmerged:
        return True, None
    if stash_after is None or stash_after == stash_before or not _is_autostash_of(stash_after, previous_head):
        # Conflicts without a new entry that is provably the autostash: the changes
        # may exist only in the conflicted files, so leave the tree for the user.
        # The fast-forward itself succeeded, so this is a result, not an error.
        logger.warning("App update: local changes conflicted and could not be confirmed in the stash")
        return False, (
            "Updated, but re-applying your local changes conflicted and they could not be confirmed in the stash. "
            f"The working tree was left as-is; resolve the conflict markers in: {', '.join(unmerged.splitlines())}"
        )
    _git("reset", "--quiet", "--hard", "HEAD")
    logger.warning(
        "App update: local changes conflicted and were left in stash %s",
        sanitise_log_value(stash_after[:12]),
    )
    return False, (
        "Your local changes conflicted with the update and were left in the stash "
        f"(stash@{{0}}, commit {stash_after[:7]}). Run 'git stash pop' to re-apply them and resolve the conflicts."
    )


def _build_result(previous: str) -> AppUpdateResult:
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
def post_update(stash: bool = False) -> AppUpdateResult:
    """Fetch and fast-forward the current branch to its upstream.

    ``stash=true`` lets a dirty working tree update by stashing the local
    changes around the fast-forward and re-applying them afterwards.
    """

    if not _update_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="An update is already in progress.")
    try:
        status = _collect_status(fetch=True)
        use_stash = stash and status.can_update_with_stash
        if not (status.can_update or use_stash):
            raise HTTPException(status_code=409, detail=status.reason)
        return _apply_update(status, stash=use_stash)
    except GitError as exc:
        logger.warning("App update failed: %s", sanitise_log_value(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        _update_lock.release()
