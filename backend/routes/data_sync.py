"""Sync the data bucket with the allotmint-data repo from the Support page (#11037).

``POST /support/data-sync/pull`` copies allotmint-data's ``main`` into the S3
data bucket (git wins); ``POST /support/data-sync/push`` copies the bucket back
into allotmint-data as a pull request. Neither runs here: each dispatches a
``workflow_dispatch`` workflow in allotmint-data (``data-pull.yml`` /
``data-push.yml``), which assumes the CDK ``DataSyncRole`` and does the
copying. The repo has thousands of files including parquet timeseries, far
too heavy for a request handler, and Actions keeps a log of every sync.

The GitHub token (fine-grained, Actions: write on allotmint-data only) is read
from the SSM SecureString named by ``DATA_SYNC_TOKEN_PARAMETER`` on AWS, or
``DATA_SYNC_GITHUB_TOKEN`` locally.

Access: these actions overwrite portfolio data, so on AWS only the owner
emails in ``allowed_emails`` may use them, and never a demo session. Unlike
the other admin routes this does not stand down when ``DISABLE_AUTH`` is set,
because the Lambda always runs with it (API Gateway does the sign-in).
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Literal, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException

from backend import auth
from backend.config import config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

Direction = Literal["pull", "push"]
WORKFLOWS: Dict[str, str] = {"pull": "data-pull.yml", "push": "data-push.yml"}
_GITHUB_API = "https://api.github.com"
_TIMEOUT_SECONDS = 15
_ACTIVE_STATUSES = {"queued", "in_progress", "waiting", "requested", "pending"}
_FORBIDDEN_DETAIL = "Only the owner can sync data with git"

_token_lock = threading.Lock()
_token_cache: Dict[str, str] = {}


# backend.auth.get_active_user, not backend.routes.get_active_user: the latter
# returns None whenever DISABLE_AUTH is set, which it always is on Lambda.
def _ensure_owner(identity: str | None = Depends(auth.get_active_user)) -> None:
    if auth.is_demo_request():
        raise HTTPException(status_code=403, detail=_FORBIDDEN_DETAIL)
    if config.disable_auth and config.app_env != "aws":
        return  # local development without sign-in
    allowed = {
        email.strip().lower() for email in (config.allowed_emails or []) if isinstance(email, str) and email.strip()
    }
    if not identity or identity.strip().lower() not in allowed:
        raise HTTPException(status_code=403, detail=_FORBIDDEN_DETAIL)


router = APIRouter(
    prefix="/support/data-sync",
    tags=["support"],
    dependencies=[Depends(_ensure_owner)],
)


def _repo() -> Optional[str]:
    return os.getenv("DATA_SYNC_REPO") or None


def _token() -> Optional[str]:
    local = os.getenv("DATA_SYNC_GITHUB_TOKEN")
    if local:
        return local
    parameter = os.getenv("DATA_SYNC_TOKEN_PARAMETER")
    if not parameter:
        return None
    with _token_lock:
        if parameter not in _token_cache:
            import boto3  # type: ignore
            from botocore.exceptions import BotoCoreError, ClientError

            try:
                response = boto3.client("ssm").get_parameter(Name=parameter, WithDecryption=True)
            except (BotoCoreError, ClientError) as exc:
                logger.warning(
                    "Could not read the data-sync token from %s: %s",
                    sanitise_log_value(parameter),
                    sanitise_log_value(exc),
                )
                return None
            _token_cache[parameter] = response["Parameter"]["Value"]
        return _token_cache[parameter]


def _github(method: str, path: str, token: str, **kwargs: Any) -> requests.Response:
    try:
        return requests.request(
            method,
            f"{_GITHUB_API}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=_TIMEOUT_SECONDS,
            **kwargs,
        )
    except requests.RequestException as exc:
        logger.warning("GitHub request failed: %s", sanitise_log_value(exc))
        raise HTTPException(status_code=424, detail="Could not reach GitHub") from exc


# GitHub failures are 424, not 502: the frontend treats 502-504 as transient
# and shows a generic message instead of this actionable detail.
def _raise_for_github(response: requests.Response, action: str) -> None:
    if response.ok:
        return
    if response.status_code in (401, 403, 404):
        # 401/403: expired or under-scoped token; 404: also what GitHub returns
        # for a private repo or workflow the token cannot see.
        _token_cache.clear()
        detail = (
            f"GitHub refused to {action} (HTTP {response.status_code}). Check that the data-sync token "
            "has not expired and has Actions: write on the data repo, and that the workflow exists on main."
        )
    else:
        detail = f"GitHub failed to {action} (HTTP {response.status_code})"
    logger.warning("%s", sanitise_log_value(detail))
    raise HTTPException(status_code=424, detail=detail)


def _configured() -> tuple[str, str]:
    repo, token = _repo(), _token()
    if not repo or not token:
        raise HTTPException(
            status_code=503,
            detail="Data sync is not configured (DATA_SYNC_REPO and the GitHub token). See docs/DEPLOY.md.",
        )
    return repo, token


def _latest_run(repo: str, token: str, workflow: str) -> Optional[Dict[str, Any]]:
    response = _github("GET", f"/repos/{repo}/actions/workflows/{workflow}/runs", token, params={"per_page": 1})
    _raise_for_github(response, f"read {workflow} runs")
    runs = response.json().get("workflow_runs") or []
    if not runs:
        return None
    run = runs[0]
    return {
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "html_url": run.get("html_url"),
        "created_at": run.get("created_at"),
        "actor": (run.get("triggering_actor") or {}).get("login"),
    }


@router.get("")
def data_sync_status() -> Dict[str, Any]:
    """Whether sync is configured, and the latest pull and push runs."""

    repo, token = _repo(), _token()
    if not repo or not token:
        return {"configured": False, "repo": repo, "runs": {}}
    return {
        "configured": True,
        "repo": repo,
        "pulls_url": f"https://github.com/{repo}/pulls",
        "runs": {direction: _latest_run(repo, token, workflow) for direction, workflow in WORKFLOWS.items()},
    }


@router.post("/{direction}", status_code=202)
def start_data_sync(direction: Direction, identity: str | None = Depends(auth.get_active_user)) -> Dict[str, Any]:
    """Dispatch the pull or push workflow, unless a sync is already running."""

    repo, token = _configured()
    # Best-effort: two near-simultaneous requests can both pass this check.
    # The workflows' shared "data-sync" concurrency group is what actually
    # serialises them; this just gives the common case a clear 409.
    for workflow in WORKFLOWS.values():
        run = _latest_run(repo, token, workflow)
        if run and run["status"] in _ACTIVE_STATUSES:
            raise HTTPException(status_code=409, detail="A data sync is already running; wait for it to finish.")

    workflow = WORKFLOWS[direction]
    response = _github(
        "POST",
        f"/repos/{repo}/actions/workflows/{workflow}/dispatches",
        token,
        json={"ref": "main", "inputs": {"requested_by": identity or "unknown"}},
    )
    _raise_for_github(response, f"start {workflow}")
    logger.info(
        "Data sync %s dispatched by %s", sanitise_log_value(direction), sanitise_log_value(identity or "unknown")
    )
    return {"dispatched": direction, "workflow": workflow, "repo": repo}
